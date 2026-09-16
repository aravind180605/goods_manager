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

def fast_compress_image(file_path, max_dim=1100):
    """
    Normalizes rotation and optimizes resolution to ~120KB.
    Dramatically increases processing speed without losing handwriting detail.
    """
    img = Image.open(file_path)
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=78, optimize=True)
    buf.seek(0)
    return Image.open(buf)

def extract_lr_details(file_path):
    """
    High-speed universal extractor with precise package count parsing.
    """
    api_key = get_api_key()
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY not found in secrets or environment.")
        return {"lr_number": "", "transport_name": "", "sender_name": "", "booking_date": "", "expected_qty": 1}

    client = genai.Client(api_key=api_key)
    optimized_image = fast_compress_image(file_path)

    # Ultra-concise prompt to minimize token generation latency
    prompt = """
    Analyze this transport receipt (bilty). Detect its correct orientation and extract these 5 fields strictly:

    1. lr_number: Alphanumeric receipt number (e.g., '114082', 'KRJKT04612'). Preserve letter prefixes.
    2. transport_name: Logistics banner / header name (e.g., 'S.S.T. LOGISTIC', 'SHIV SHANKAR').
    3. sender_name: Consignor / Sender name from 'Consignor Name & Address' or 'From'.
    4. booking_date: Date in DD-MM-YYYY format.
    5. expected_qty: Locate the 'No. of Packages' / 'Articles' column. 
       - Read the handwritten number inside brackets/circles or next to units (e.g. '(3)', '3 Thaan', '3 Parcel', '4 Box', '10 Bales').
       - Quantity is the article count (e.g. 3).
       - Never use Weight (150 kg), Freight charges (35, 15), or vehicle numbers.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[optimized_image, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {
                        "lr_number": {"type": "STRING"},
                        "transport_name": {"type": "STRING"},
                        "sender_name": {"type": "STRING"},
                        "booking_date": {"type": "STRING"},
                        "expected_qty": {"type": "INTEGER"}
                    },
                    "required": ["lr_number", "expected_qty"]
                },
                temperature=0.0
            )
        )
        data = json.loads(response.text.strip())
    except Exception as e:
        st.error(f"Gemini API Error: {e}")
        data = {}

    clean_lr = re.sub(r'[^A-Z0-9\-\/]', '', str(data.get("lr_number", ""))).strip().upper()
    
    # Strictly validate positive package quantity
    raw_qty = data.get("expected_qty", 1)
    try:
        clean_qty = int(raw_qty)
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