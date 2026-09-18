import json
import os
import re
import io
from PIL import Image, ImageOps
import streamlit as st
from google import genai
from google.genai import types

def get_api_key():
    """Safely reads the Gemini API key from environment variables or Streamlit secrets."""
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return env_key
    try:
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return ""

def fast_compress_image(image_input, max_dim=1100):
    """Normalizes EXIF orientation and balances compression to retain handwritten details."""
    if isinstance(image_input, (str, os.PathLike)):
        img = Image.open(image_input)
    else:
        if hasattr(image_input, "seek"):
            image_input.seek(0)
        img = Image.open(image_input)

    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / float(max(w, h))
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80, optimize=True)
    buf.seek(0)
    return Image.open(buf)

def extract_lr_details(image_input):
    """Parses receipt data using Gemini 2.5 Flash."""
    api_key = get_api_key()
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY missing! Add it to .streamlit/secrets.toml or Streamlit Cloud Secrets.")
        return {"lr_number": "", "transport_name": "", "sender_name": "", "booking_date": "", "expected_qty": 1}

    try:
        client = genai.Client(api_key=api_key)
        optimized_image = fast_compress_image(image_input)

        prompt = """
        Analyze this transport receipt / LR / Bilty (printed or handwritten).
        Extract these 5 fields strictly in valid JSON:
        
        1. "lr_number": Receipt/Consignment/Bkg number. Retain letters and numbers.
        2. "transport_name": Carrier/transport company name banner.
        3. "sender_name": Consignor/Sender name next to "Consignor's Name" or "From".
        4. "booking_date": Booking date formatted as DD-MM-YYYY.
        5. "expected_qty": Total package count under 'No. of Packages' / 'Articles' (integer only). Do NOT extract weight (e.g. 150 kg) or freight charges.

        Output strictly a single JSON object with keys: lr_number, transport_name, sender_name, booking_date, expected_qty.
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[optimized_image, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        
        raw_text = response.text.strip() if response and response.text else "{}"
        data = json.loads(raw_text)
    except Exception as e:
        st.error(f"Gemini API Notice: {e}")
        data = {}

    clean_lr = re.sub(r'[^A-Z0-9\-\/]', '', str(data.get("lr_number", ""))).strip().upper()
    
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