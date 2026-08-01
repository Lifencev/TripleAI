import streamlit as st
import pandas as pd
import requests
import os
import json
from dotenv import load_dotenv

# Імпортуємо ваші модулі
from news2 import news2
from time_interval import next_eval_interval
from prompts import SYSTEM_PROMPT

# --- Environment Setup ---
load_dotenv()
SPUR_API_KEY = os.getenv("SPUR_GEMMA_4_KEY")
API_URL = "https://ai.spuric.com/v1/chat/completions"

st.set_page_config(page_title="Triage Re-Evaluation Copilot", page_icon="🏥", layout="wide")

# Шлях до вашого CSV файлу (змініть назву, якщо потрібно)
CSV_FILE_PATH = "./data/processed/triage_features_control.csv" 

# --- Core Logic ---
def calculate_patient_metrics(row):
    """Раховує NEWS2 та інтервал перевірки для окремого рядка пацієнта з CSV."""
    rr = row.get('triage_rr', row.get('RR', 16))
    spo2 = row.get('triage_spo2', row.get('Saturation', 98))
    o2 = row.get('triage_on_oxygen', row.get('O2_supp', False))
    sbp = row.get('triage_sbp', row.get('SBP', 120))
    hr = row.get('triage_hr', row.get('HR', 80))
    temp = row.get('triage_temp_c', row.get('Temp', 36.6))
    alert = row.get('alert', True)
    
    # 1. Раховуємо NEWS2
    news2_res = news2(rr, spo2, o2, sbp, hr, temp, alert)
    score = news2_res['aggregate']
    max_param = news2_res['max_single_param']
    
    # 2. Раховуємо інтервал через time_interval.py
    esi = int(row.get('esi_level', 3))
    interval_data = next_eval_interval(score, max_param, esi)
    
    return {
        "NEWS2_Score": score,
        "Max_Single_Param": max_param,
        "Reeval_Interval_Min": interval_data['interval_min'],
        "Interval_Driver": interval_data['driver']
    }

def insert_patient_into_queue(queue_df, new_patient_row):
    """
    Додає нового пацієнта до існуючої черги і сортує її 
    за пріоритетом (найвищий NEWS2, за ним — найкоротший інтервал).
    """
    # Рахуємо метрики для нового пацієнта
    metrics = calculate_patient_metrics(new_patient_row)
    
    # Об'єднуємо дані рядка з розрахованими метриками
    patient_dict = new_patient_row.to_dict()
    patient_dict.update(metrics)
    
    # Додаємо до поточного DataFrame черги
    new_row_df = pd.DataFrame([patient_dict])
    updated_queue = pd.concat([queue_df, new_row_df], ignore_index=True)
    
    # Сортуємо чергу згідно з правилами (високий бал та короткий інтервал йдуть нагору)
    return updated_queue.sort_values(
        by=['NEWS2_Score', 'Reeval_Interval_Min'], 
        ascending=[False, True]
    ).reset_index(drop=True)

def generate_focus_note(patient_row):
    """Формує JSON та викликає Gemma API згідно з prompts.py (безпечно обробляє NaN)."""
    history = []
    for col in ['Chief_complain', 'chief_complaints', 'relevant_history']:
        if col in patient_row and pd.notna(patient_row[col]):
            val = str(patient_row[col])
            history.extend([h.strip() for h in val.split('|')])
    history = list(set(history))
    if not history:
        history = ["No specific history provided"]

    # Безпечне отримання початкових та гірших показників (з перевіркою на NaN)
    hr_triage = patient_row.get('triage_hr', patient_row.get('HR', 0))
    if pd.isna(hr_triage): hr_triage = 0
    
    hr_worst = patient_row.get('worst_hr', hr_triage)
    if pd.isna(hr_worst): hr_worst = hr_triage

    rr_triage = patient_row.get('triage_rr', patient_row.get('RR', 0))
    if pd.isna(rr_triage): rr_triage = 0
    
    rr_worst = patient_row.get('worst_rr', rr_triage)
    if pd.isna(rr_worst): rr_worst = rr_triage

    spo2_triage = patient_row.get('triage_spo2', patient_row.get('Saturation', 100))
    if pd.isna(spo2_triage): spo2_triage = 100
    
    spo2_worst = patient_row.get('worst_spo2', spo2_triage)
    if pd.isna(spo2_worst): spo2_worst = spo2_triage

    drivers = []
    if hr_worst > hr_triage:
        drivers.append({"param": "heart rate", "from": int(hr_triage), "to": int(hr_worst)})
    if rr_worst > rr_triage:
        drivers.append({"param": "resp rate", "from": int(rr_triage), "to": int(rr_worst)})
    if spo2_worst < spo2_triage:
        drivers.append({"param": "SpO2", "from": int(spo2_triage), "to": int(spo2_worst)})
    
    # Якщо пацієнт стабільний і драйверів немає, додаємо базовий статус для промпту
    if not drivers:
        drivers.append({"param": "vitals stable", "from": int(hr_triage), "to": int(hr_triage)})

    prev_score = int(patient_row.get('triage_news2', patient_row.get('NEWS2_Score', 0)))
    if pd.isna(prev_score): prev_score = 0
    
    now_score = int(patient_row.get('worst_news2', prev_score))
    if pd.isna(now_score): now_score = prev_score
    
    interval_min = patient_row.get('Reeval_Interval_Min', 60)
    driver = patient_row.get('Interval_Driver', 'NEWS2')
    interval_status_str = f"reassessment required within {interval_min} min, governed by {driver}"

    patient_json_data = {
        "patient": str(patient_row.get('Name', f"Patient {patient_row.get('source_row_id', 'Unknown')}")),
        "news2_prev": prev_score,
        "news2_now": now_score,
        "drivers": drivers,
        "relevant_history": history,
        "interval_status": interval_status_str
    }
    
    formatted_prompt = SYSTEM_PROMPT.replace("{JSON}", json.dumps(patient_json_data))
    
    headers = {"Authorization": f"Bearer {SPUR_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "spur-gemma4", "messages": [{"role": "user", "content": formatted_prompt}]}
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"System Alert: Check patient vitals immediately. Error: {e}"

def highlight_critical_patients(row):
    """CSS підсвічування для критичних пацієнтів у таблиці."""
    if row['NEWS2_Score'] >= 5 or row.get('Max_Single_Param', 0) == 3:
        return ['background-color: rgba(255, 75, 75, 0.3)'] * len(row)
    return [''] * len(row)

# --- Session State Initialization ---
if "queue" not in st.session_state:
    st.session_state.queue = pd.DataFrame() # Початково черга порожня!
if "csv_index" not in st.session_state:
    st.session_state.csv_index = 0          # Вказівник на поточний рядок у CSV
if "note_patient_id" not in st.session_state:
    st.session_state.note_patient_id = None
if "note_patient_score" not in st.session_state:
    st.session_state.note_patient_score = None
if "current_note" not in st.session_state:
    st.session_state.current_note = None

# --- Streamlit UI ---
st.title("🏥 Triage Re-Evaluation Copilot")
st.markdown("Sequential ER Intake. Patients are fetched from CSV and dynamically inserted into the risk-ranked queue.")

tab_focus, tab_macro = st.tabs(["🩺 Next Action Required", "📋 Risk-Ranked Queue (Macro View)"])

# --- Window 1: Current Patient ---
with tab_focus:
    st.header("Immediate Triage Action")
    
    # Кнопка для завантаження наступного пацієнта з CSV файлу
    if st.button("📥 Fetch Next Patient from Intake", type="primary"):
        try:
            # Читаємо файл послідовно по одному рядку за допомогою skiprows та nrows
            df_chunk = pd.read_csv(CSV_FILE_PATH, skiprows=range(1, st.session_state.csv_index + 1), nrows=1)
            
            if not df_chunk.empty:
                new_patient = df_chunk.iloc[0]
                # Додаємо пацієнта в чергу з урахуванням його інтервалу та сортування
                st.session_state.queue = insert_patient_into_queue(st.session_state.queue, new_patient)
                # Збільшуємо індекс для наступного натискання
                st.session_state.csv_index += 1
                st.rerun()
            else:
                st.warning("No more patients left in the intake CSV file.")
        except Exception as e:
            st.error(f"Error reading CSV file: {e}. Ensure '{CSV_FILE_PATH}' is in the project folder.")

    st.divider()

    if not st.session_state.queue.empty:
        top_patient = st.session_state.queue.iloc[0]
        
        st.error(f"**Re-evaluate immediately:** Patient ID {top_patient.get('source_row_id', 'Unknown')} (NEWS2: {top_patient['NEWS2_Score']}, Interval: {top_patient['Reeval_Interval_Min']}m)")
        
        # Автоматична генерація нотатки для нового лідера черги
        patient_unique_key = f"{top_patient.get('source_row_id', 0)}_{top_patient['NEWS2_Score']}"
        if st.session_state.note_patient_id != patient_unique_key:
            with st.spinner("Gemma is synthesizing context..."):
                st.session_state.current_note = generate_focus_note(top_patient)
                st.session_state.note_patient_id = patient_unique_key

        st.info(f"**Gemma Focus Note:** {st.session_state.current_note}")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("✅ Acknowledge & Clear Patient", width="stretch"):
                st.session_state.queue = st.session_state.queue.iloc[1:].reset_index(drop=True)
                st.session_state.note_patient_id = None
                st.rerun()
                
        with col_btn2:
            if st.button("⏸️ Keep in Queue (No Action)", width="stretch"):
                st.rerun()
                
        st.divider()
        st.subheader("Critical Vitals Snapshot")
        col_v1, col_v2, col_v3 = st.columns(3)
        col_v1.metric("NEWS2 Score", top_patient['NEWS2_Score'])
        col_v2.metric("SpO2", f"{top_patient.get('triage_spo2', top_patient.get('Saturation', 'N/A'))}%")
        col_v3.metric("Heart Rate", top_patient.get('triage_hr', top_patient.get('HR', 'N/A')))
        
    else:
        st.info("The waiting room queue is currently empty. Click **'Fetch Next Patient from Intake'** above to admit a patient from the CSV.")

# --- Window 2: Whole Picture ---
with tab_macro:
    st.header("Overall ER Status")
    st.write("Patients are dynamically inserted and sorted by their NEWS2 score and mandatory re-evaluation interval.")
    
    if not st.session_state.queue.empty:
        styled_queue = st.session_state.queue.style.apply(highlight_critical_patients, axis=1)
        st.dataframe(styled_queue, width="stretch", hide_index=True)
    else:
        st.write("No patients currently in the waiting room.")