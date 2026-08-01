import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()
SPUR_API_KEY = os.getenv("SPUR_GEMMA_4_KEY")
API_URL = "https://ai.spuric.com/v1/chat/completions"

st.set_page_config(page_title="Triage In Light Speed", page_icon="🏥", layout="wide")

# --- Helper Functions ---
@st.cache_data
def load_patient_data():
    """
    Loads the patient CSV file, handling specific European formatting 
    such as semicolon delimiters and comma decimal separators.
    """
    try:
        # delimiter=';' handles the semicolon-separated columns
        # decimal=',' parses European number formats (e.g., 5,00 -> 5.0)
        # encoding='latin-1' avoids UnicodeDecodeError for special characters
        return pd.read_csv(
            "data/raw/data.csv", 
            delimiter=";", 
            decimal=",", 
            encoding="latin-1"
        )
    except FileNotFoundError:
        # Fallback to empty dataframe with the actual dataset columns
        return pd.DataFrame(columns=[
            "Group", "Sex", "Age", "Patients number per hour", "Arrival mode", 
            "Injury", "Chief_complain", "Mental", "Pain", "NRS_pain", "SBP", 
            "DBP", "HR", "RR", "BT", "Saturation", "KTAS_RN", "Diagnosis in ED", 
            "Disposition", "KTAS_expert", "Error_group", "Length of stay_min", 
            "KTAS duration_min", "mistriage"
        ])

def get_gemma_rationale(patient_record):
    """Sends patient data to Gemma 4 to get a clinical triage assessment."""
    if not SPUR_API_KEY:
        return "Error: SPUR_GEMMA_4_KEY missing in .env file."
        
    # Динамічно підставляємо реальні колонки з вашого data.csv
    prompt = f"""
    You are an expert ER triage AI. Assess this patient and explain why they need priority care.
    Keep the explanation under 3 sentences. State a priority level (1-Critical to 5-Non-Urgent).
    
    Patient Details:
    Age: {patient_record.get('Age', 'Unknown')}
    Chief Complain: {patient_record.get('Chief_complain', 'Unknown')}
    Pain Level (NRS): {patient_record.get('NRS_pain', 'Unknown')}
    Vitals: 
      - Heart Rate: {patient_record.get('HR', 'Unknown')}
      - Blood Pressure: {patient_record.get('SBP', 'Unknown')} / {patient_record.get('DBP', 'Unknown')}
      - Temp: {patient_record.get('BT', 'Unknown')} °C
      - Oxygen Sat: {patient_record.get('Saturation', 'Unknown')}%
    """
    
    headers = {
        "Authorization": f"Bearer {SPUR_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Стандартний формат payload для Chat Completions
    payload = {
        "model": "spur-gemma4", # <--- Назва моделі передається саме тут!
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status() # Зупинить виконання і покаже помилку, якщо статус не 200 OK
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"AI Assessment failed: {e}"

# --- State Initialization ---
if "patient_db" not in st.session_state:
    st.session_state.patient_db = load_patient_data()
if "current_index" not in st.session_state:
    st.session_state.current_index = 0
if "current_patient" not in st.session_state:
    st.session_state.current_patient = None

# --- UI Layout ---
st.title("🏥 Clinical ER Triage System")

tab_focus, tab_macro = st.tabs(["🩺 Current Patient Assessment", "📋 ER Macro View"])

# --- Window 1: Current Patient ---
with tab_focus:
    st.header("Immediate Triage")
    
    # Button to fetch the next patient from the CSV
    # Replace deprecated parameter in buttons and dataframes

    if st.button("🚨 Fetch Next Patient", type="primary", width="stretch"):
        if st.session_state.current_index < len(st.session_state.patient_db):
            # Grab the next patient row as a dictionary
            raw_record = st.session_state.patient_db.iloc[st.session_state.current_index].to_dict()
            
            # Trigger the API call with a loading spinner
            with st.spinner("Gemma 4 is analyzing patient data..."):
                ai_assessment = get_gemma_rationale(raw_record)
            
            # Save the processed data to session state for the UI
            st.session_state.current_patient = {
                "name": raw_record.get("Name", "Unknown"),
                "details": raw_record,
                "ai_notes": ai_assessment
            }
            
            # Increment index so the next click gets the next patient
            st.session_state.current_index += 1
            st.rerun()
        else:
            st.warning("No more patients in the queue.")
        
    # Visualization of current patient
    if st.session_state.current_patient:
        st.divider()
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Patient Vitals & Intake")
            # Dynamically display all columns from the CSV
            for key, value in st.session_state.current_patient["details"].items():
                st.write(f"**{key}:** {value}")
            
        with col2:
            st.subheader("Gemma AI Assessment")
            st.info(st.session_state.current_patient["ai_notes"])

# --- Window 2: Whole Picture ---
with tab_macro:
    st.header("Overall ER Status")
    st.write("All raw patient records from the CSV dataset.")

    st.dataframe(st.session_state.patient_db, hide_index=True, width="stretch")