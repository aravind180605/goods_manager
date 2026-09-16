import json
import os
import re
import io
from PIL import Image, ImageOps
import streamlit as st
from google import genai
from google.genai import types

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
    High-speed universal LR Extractor using the modern Gemini 2.5 Flash API.
    """
    api_key = get_api_key()
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY not configured! Add it to .streamlit/secrets.toml or Streamlit Cloud Secrets.")
        return {"lr_number": "", "transport_name": "", "sender_name": "", "booking_date": "", "expected_qty": 1}

    # Initialize client with current google-genai SDK
    client = genai.Client(api_key=api_key)
    optimized_image = preprocess_and_compress(file_path)

    prompt = """
    Analyze this Indian Lorry Receipt / Transport Bilty (horizontal, vertical, or rotated).
    Extract these 5 fields strictly as JSON:
    
    1. "lr_number": 
       - Consignment Note / LR Number / Bkg No / GR Number (e.g., '114082', 'KRJKT04612', 'KSHPR00411').
       - Keep both letters and numbers if present. Do not include labels like 'No.'.

    2. "transport_name": 
       - Logistics or transport company banner (e.g., 'S.S.T. LOGISTIC', 'SHIV SHANKAR TRANSPORT').

    3. "sender_name": 
       - Consignor / Sender name next to 'Consignor's Name & Address' or 'From' (e.g., 'PRITHVI SUITING', 'OKK', 'LALIT BHAI').

    4. "booking_date": 
       - Booking date formatted as DD-MM-YYYY (e.g., '14-08-2026').

    5. "expected_qty": 
       - Package count declared in 'No. of Packages' / 'Articles' / 'Description'.
       - Look for handwritten count, circled notation, or text like '(3)', '3 Thaan', '3 Parcel', '5 Box'.
       - Return strictly the package count as an integer (e.g., 3). Do NOT take weight (150 kg) or charges.

    Return JSON format only:
    {"lr_number": "", "transport_name": "", "sender_name": "", "booking_date": "", "expected_qty": 1}
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[optimized_image, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )
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