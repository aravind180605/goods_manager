import json
import os
from PIL import Image
import streamlit as st
from google import genai
from google.genai import types

def extract_lr_details(file_path):
    """
    Extracts Lorry Receipt (LR) data using Google Gemini Vision API.
    Reads API key securely from st.secrets or environment variable GEMINI_API_KEY.
    """
    api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    
    if not api_key:
        st.warning("⚠️ GEMINI_API_KEY not found in Streamlit secrets. Manual entry required.")
        return {
            "lr_number": "",
            "transport_name": "SHIV SHANKAR",
            "sender_name": "",
            "booking_date": "",
            "expected_qty": 1
        }

    client = genai.Client(api_key=api_key)
    image = Image.open(file_path)

    prompt = """
    You are an expert logistics data entry assistant. Analyze this Indian Lorry Receipt (LR) / Consignment Note image.
    Extract the following information accurately in JSON format:
    - "lr_number": Consignment / LR / Bkg No / Note Number.
    - "transport_name": Name of the logistics / transport company (e.g., "S.S.T. LOGISTIC", "SHIV SHANKAR").
    - "sender_name": Consignor / Sender company or person name. Standardize known variations (e.g., if 'OOK', '0KK', 'O0K', standardize to 'OKK').
    - "booking_date": Date of booking in DD-MM-YYYY format.
    - "expected_qty": Total numeric count of packages/cartons/bales/thaan/articles (integer only). Do not confuse with weight (kgs) or freight amount.

    Return ONLY a single valid raw JSON object without markdown fences or additional explanation.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        raw_text = response.text.strip()
        data = json.loads(raw_text)
    except Exception as e:
        st.error(f"Gemini Vision extraction error: {e}")
        data = {}

    return {
        "lr_number": str(data.get("lr_number", "")).strip().upper(),
        "transport_name": str(data.get("transport_name", "SHIV SHANKAR")).strip().upper(),
        "sender_name": str(data.get("sender_name", "")).strip().upper(),
        "booking_date": str(data.get("booking_date", "")).strip(),
        "expected_qty": int(data.get("expected_qty", 1) or 1)
    }