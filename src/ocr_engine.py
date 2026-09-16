import json
import os
import re
import io
from PIL import Image, ImageOps
import streamlit as st
import google.generativeai as genai

def get_api_key():
    """Safely retrieves the Gemini API key across local and cloud environments."""
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return env_key
    try:
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return ""

def preprocess_and_compress(file_path, max_dim=1280):
    """
    Normalizes EXIF orientation and resizes image to max 1280px.
    Accelerates API upload and response time.
    """
    img = Image.open(file_path)
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
    
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85, optimize=True)
    buffer.seek(0)
    return Image.open(buffer)

def extract_lr_details(file_path):
    """
    Universal LR Extractor capturing full alphanumeric LR numbers (letters + numbers),
    sender details, booking dates, and verified package quantities.
    """
    api_key = get_api_key()
    if not api_key:
        st.warning("⚠️ GEMINI_API_KEY not configured. Add it to .streamlit/secrets.toml or Streamlit Cloud Secrets.")
        return {"lr_number": "", "transport_name": "", "sender_name": "", "booking_date": "", "expected_qty": 1}

    # Configure the Gemini API client
    genai.configure(api_key=api_key)
    optimized_image = preprocess_and_compress(file_path)

    prompt = """
    Analyze this Indian Lorry Receipt / Transport Bilty (horizontal, vertical, or rotated).
    Extract these 5 fields strictly as JSON:
    
    1. "lr_number": 
       - Consignment Note / LR Number / Bkg No / GR Number.
       - IMPORTANT: The LR number frequently contains BOTH LETTERS AND DIGITS together (e.g., 'KRJKT04612', 'KSHPR00411', 'AHM89012', 'BOM1042') or purely digits (e.g., '114082').
       - DO NOT drop, omit, or trim the letter prefix/suffix. Capture the full alphanumeric identifier exactly as written/stamped.
       - Do not include field labels like 'LR No' or 'No:'.

    2. "transport_name": 
       - Logistics or transport company banner (e.g., 'S.S.T. LOGISTIC', 'SHIV SHANKAR TRANSPORT').

    3. "sender_name": 
       - Consignor / Sender name next to 'Consignor's Name & Address' or 'From' (e.g., 'PRITHVI SUITING', 'OKK', 'LALIT BHAI').

    4. "booking_date": 
       - Booking date formatted as DD-MM-YYYY (e.g., '14-08-2026').

    5. "expected_qty": 
       - Count declared in 'No. of Packages' / 'Articles' / 'Description'.
       - Look for handwritten values or circled notations like '(3)', '3 Thaan', '3 Parcel', '5 Box', '12 Cartons'.
       - Return strictly the package count as an integer (e.g., 3). Ignore weights (e.g., 150 kg), rate, or freight amounts.

    Return JSON format only:
    {"lr_number": "", "transport_name": "", "sender_name": "", "booking_date": "", "expected_qty": 1}
    """

    try:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={"response_mime_type": "application/json", "temperature": 0.0}
        )
        response = model.generate_content([optimized_image, prompt])
        data = json.loads(response.text.strip())
    except Exception as e:
        st.error(f"Gemini API Error: {e}")
        data = {}

    raw_lr = str(data.get("lr_number", "")).strip().upper()
    clean_lr = re.sub(r'[^A-Z0-9\-\/]', '', raw_lr)
    
    try:
        clean_qty = int(data.get("expected_qty", 1))
        if clean_qty <= 0:
            clean_qty = 1
    except (ValueError, TypeError):
        clean_qty = 1

    return {
        "lr_number": clean_lr,
        "transport_name": str(data.get("transport_name", "")).strip().upper(),
        "sender_name": str(data.get("sender_name", "")).strip().upper(),
        "booking_date": str(data.get("booking_date", "")).strip(),
        "expected_qty": clean_qty
    }