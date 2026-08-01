import streamlit as st
import pandas as pd
import requests
import os
import random
from dotenv import load_dotenv
import json

# Import the deterministic NEWS2 calculator
from news2 import news2
from prompts import SYSTEM_PROMPT 

# --- Environment Setup ---
load_dotenv()
SPUR_API_KEY = os.getenv("SPUR_GEMMA_4_KEY")
API_URL = "https://ai.spuric.com/v1/chat/completions"

st.set_page_config(page_title="Triage Re-Evaluation Copilot", page_icon="🏥", layout="wide")

# --- Core Logic & State Management ---
def recalculate_and_sort_queue(df):
    """Applies the deterministic NEWS2 rules to the dataframe and sorts it."""
    if df.empty:
        return df
        
    scores = []
    max_params = []
    
    for _, row in df.iterrows():
        result = news2(row['RR'], row['SpO2'], row['O2_supp'], row['SBP'], row['HR'], row['Temp'], row['Alert'])
        scores.append(result['aggregate'])
        max_params.append(result['max_single_param'])
        
    df['NEWS2_Score'] = scores
    df['Max_Single_Param'] = max_params
    
    # Sort: Highest score first.
    return df.sort_values(by='NEWS2_Score', ascending=False).reset_index(drop=True)

def initialize_mock_data():
    """Generates the initial waiting room state with an expanded patient roster."""
    data = [
        {"ID": "P001", "Name": "John Doe", "Age": 68, "RR": 22, "SpO2": 92, "O2_supp": True, "SBP": 105, "HR": 115, "Temp": 38.2, "Alert": True, "Chief_complain": "COPD Exacerbation"},
        {"ID": "P002", "Name": "Jane Smith", "Age": 45, "RR": 16, "SpO2": 98, "O2_supp": False, "SBP": 120, "HR": 85, "Temp": 36.6, "Alert": True, "Chief_complain": "Ankle sprain"},
        {"ID": "P003", "Name": "Bob Lee", "Age": 75, "RR": 26, "SpO2": 89, "O2_supp": False, "SBP": 88, "HR": 135, "Temp": 39.1, "Alert": False, "Chief_complain": "Sepsis protocol"},
        {"ID": "P004", "Name": "Alice Wong", "Age": 32, "RR": 18, "SpO2": 99, "O2_supp": False, "SBP": 115, "HR": 72, "Temp": 37.0, "Alert": True, "Chief_complain": "Mild abdominal pain"},
        {"ID": "P005", "Name": "David Kim", "Age": 52, "RR": 14, "SpO2": 96, "O2_supp": False, "SBP": 145, "HR": 90, "Temp": 37.1, "Alert": True, "Chief_complain": "Severe back pain"},
        {"ID": "P006", "Name": "Sarah Jenkins", "Age": 28, "RR": 20, "SpO2": 100, "O2_supp": False, "SBP": 110, "HR": 105, "Temp": 38.5, "Alert": True, "Chief_complain": "Fever and chills"},
        {"ID": "P007", "Name": "Michael Chang", "Age": 81, "RR": 24, "SpO2": 94, "O2_supp": True, "SBP": 95, "HR": 110, "Temp": 36.2, "Alert": False, "Chief_complain": "Altered mental status"},
        {"ID": "P008", "Name": "Emily Davis", "Age": 19, "RR": 16, "SpO2": 99, "O2_supp": False, "SBP": 120, "HR": 75, "Temp": 36.8, "Alert": True, "Chief_complain": "Wrist injury"}
    ]
    df = pd.DataFrame(data)
    return recalculate_and_sort_queue(df)

def generate_focus_note(patient):
    """Gemma API call using the structured JSON prompt."""
    
    # Construct the JSON payload required by the prompt.
    # Note: Since we don't have historical data in the MVP yet, 
    # we represent prev/now as the current score to fulfill the prompt structure.
    patient_data = {
        "patient": patient['Name'],
        "news2_prev": "N/A", # Placeholder until historical data is added
        "news2_now": int(patient['NEWS2_Score']),
        "drivers": [
            # In a real app, you would diff the old and new vitals here.
            {"param": "Current Vitals", "state": f"RR {patient['RR']}, SpO2 {patient['SpO2']}%, SBP {patient['SBP']}, HR {patient['HR']}, Temp {patient['Temp']}°C"}
        ],
        "relevant_history": [patient['Chief_complain']],
        "interval_status": "Immediate re-evaluation required based on current NEWS2."
    }
    
    # Inject the JSON into the system prompt
    formatted_prompt = SYSTEM_PROMPT.replace("{patient_json}", json.dumps(patient_data))
    
    headers = {"Authorization": f"Bearer {SPUR_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "spur-gemma4", "messages": [{"role": "user", "content": formatted_prompt}]}
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"System Alert: Check patient vitals immediately. Error: {e}"

def highlight_critical_patients(row):
    """Pandas CSS styling."""
    if row['NEWS2_Score'] >= 5 or row['Max_Single_Param'] == 3:
        return ['background-color: rgba(255, 75, 75, 0.3)'] * len(row)
    return [''] * len(row)

# --- Session State Initialization ---
if "queue" not in st.session_state:
    st.session_state.queue = initialize_mock_data()
if "current_note" not in st.session_state:
    st.session_state.current_note = None

# --- Streamlit UI ---
st.title("🏥 Triage Re-Evaluation Copilot")
st.markdown("Monitoring the waiting room. Reassessment queue prioritized by NEWS2 deterioration.")

tab_focus, tab_macro = st.tabs(["🩺 Next Action Required", "📋 Risk-Ranked Queue (Macro View)"])

# --- Window 1: Current Patient ---
with tab_focus:
    if not st.session_state.queue.empty:
        st.header("Immediate Triage Action")
        top_patient = st.session_state.queue.iloc[0]
        
        st.error(f"**Re-evaluate immediately:** {top_patient['Name']} (NEWS2: {top_patient['NEWS2_Score']})")
        
        # Action Buttons (Now separated into 3 columns)
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        
        with col_btn1:
            if st.button("🧠 Generate Copilot Focus Note", type="primary", width="stretch"):
                with st.spinner("Gemma is synthesizing context..."):
                    st.session_state.current_note = generate_focus_note(top_patient)
        
        with col_btn2:
            if st.button("✅ Acknowledge & Clear Patient", width="stretch"):
                # Remove the top patient and reset the AI note
                st.session_state.queue = st.session_state.queue.iloc[1:].reset_index(drop=True)
                st.session_state.current_note = None
                st.rerun()
                
        with col_btn3:
            if st.button("⏸️ Don't Change Priority", width="stretch"):
                # Clear the note and refresh, but keep the patient exactly where they are in the queue
                st.session_state.current_note = None
                st.rerun()

        # Display the AI note if it exists
        if st.session_state.current_note:
            st.info(f"**Gemma Focus Note:** {st.session_state.current_note}")
                
        st.divider()
        st.subheader("Critical Vitals Snapshot")
        col_v1, col_v2, col_v3 = st.columns(3)
        col_v1.metric("NEWS2 Score", top_patient['NEWS2_Score'])
        col_v2.metric("SpO2", f"{top_patient['SpO2']}%")
        col_v3.metric("Heart Rate", top_patient['HR'])
        
    else:
        st.success("The waiting room is currently clear. No patients require immediate re-evaluation.")
        if st.button("Reset Demo Data"):
            st.session_state.queue = initialize_mock_data()
            st.rerun()

# --- Window 2: Whole Picture ---
with tab_macro:
    st.header("Overall ER Status")
    
    # The killer feature for the demo: Simulating deterioration
    if st.button("⚠️ Simulate Patient Deterioration", help="Forces a stable patient's vitals to crash to demonstrate the dynamic queue."):
        if len(st.session_state.queue) > 1:
            # Find the patient at the bottom of the queue (most stable)
            last_idx = len(st.session_state.queue) - 1
            
            # Drastically worsen their vitals
            st.session_state.queue.at[last_idx, 'SpO2'] = random.randint(85, 89)
            st.session_state.queue.at[last_idx, 'RR'] = random.randint(25, 30)
            st.session_state.queue.at[last_idx, 'HR'] = random.randint(130, 145)
            
            # Recalculate and sort immediately
            st.session_state.queue = recalculate_and_sort_queue(st.session_state.queue)
            st.rerun()
    
    st.write("Patients are dynamically sorted by their NEWS2 deterioration risk. High-risk patients are highlighted in red.")
    
    if not st.session_state.queue.empty:
        styled_queue = st.session_state.queue.style.apply(highlight_critical_patients, axis=1)
        st.dataframe(styled_queue, width="stretch", hide_index=True)