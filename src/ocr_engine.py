import re
import cv2
import numpy as np
import streamlit as st
from paddleocr import PaddleOCR

@st.cache_resource(show_spinner=False)
def load_ocr_model():
    """
    Initializes PaddleOCR without MKLDNN to prevent 
    'RuntimeError: could not execute a primitive' on virtual cloud containers.
    """
    return PaddleOCR(
        use_angle_cls=False,
        enable_mkldnn=False,
        use_gpu=False,
        lang='en',
        show_log=False
    )

def extract_lr_details(file_path):
    ocr = load_ocr_model()

    # Preprocess & downscale high-resolution phone camera images to prevent OOM/primitive crash
    img = cv2.imread(file_path)
    if img is not None:
        h, w = img.shape[:2]
        max_dim = 1600
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            cv2.imwrite(file_path, img)

    # Run OCR with cls=False to bypass oneDNN classifier primitive failures
    result = ocr.ocr(file_path, cls=False)

    extracted_lines = []
    if result and result[0]:
        for line in result[0]:
            text = line[1][0].strip()
            if text:
                extracted_lines.append(text)

    full_text = "\n".join(extracted_lines)
    transport_name = "SHIV SHANKAR"

    # --- 1. Extract LR Number ---
    lr_number = ""
    lr_code_match = re.search(r'\b(K[A-Z]{3,5}\d{3,7})\b', full_text, re.IGNORECASE)
    if lr_code_match:
        lr_number = lr_code_match.group(1).upper()
    else:
        for i, line in enumerate(extracted_lines):
            clean = re.sub(r'[^A-Za-z0-9]', '', line).upper()
            if "LRNO" in clean or "GRNO" in clean or "BKGNO" in clean:
                for offset in [1, 2, -1]:
                    if 0 <= i + offset < len(extracted_lines):
                        cand = re.sub(r'[^A-Za-z0-9]', '', extracted_lines[i + offset]).upper()
                        if cand not in ["REMARKS", "ROUTE", "GSTIN", "CONSIGNEE", "DATE"] and len(cand) >= 5:
                            lr_number = cand
                            break
                if lr_number:
                    break

    # --- 2. Extract Booking Date ---
    booking_date = ""
    date_match = re.search(r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', full_text)
    if date_match:
        booking_date = date_match.group(1).replace('/', '-')

    # --- 3. Extract Consigner (Sender) ---
    sender_name = ""
    known_senders = re.search(r'\b(OKK|OOK|0KK|LALIT\s*BHAI|SHREE\s*NIVASH|SHREENIVASH)\b', full_text, re.IGNORECASE)
    if known_senders:
        raw_match = known_senders.group(1).upper()
        if raw_match in ["OOK", "0KK", "O0K", "O.K.K"]:
            sender_name = "OKK"
        else:
            sender_name = raw_match
    else:
        for i, line in enumerate(extracted_lines):
            if re.search(r'Consi[gq]ner', line, re.IGNORECASE):
                for offset in range(1, 4):
                    if i + offset < len(extracted_lines):
                        cand = extracted_lines[i + offset].strip()
                        if not re.search(r'(Booking|Consignee|Description|Articles|Route|GSTIN|Date|Phone)', cand, re.IGNORECASE):
                            sender_name = cand
                            break
                if sender_name:
                    break

    # --- 4. Robust Quantity of Articles Extraction ---
    expected_qty = 1
    found_qty = False

    # Check for keywords like "3 BOX", "12 CARTONS", "5 CTNS", "2 PKTS"
    unit_match = re.search(r'\b(\d{1,3})\s*(?:BUNDLES?|BAGS?|BOX(?:ES)?|CARTONS?|CTNS?|PKTS?|PARCELS?|PCS|ARTICLES?)\b', full_text, re.IGNORECASE)
    if unit_match:
        val = int(unit_match.group(1))
        if 1 <= val <= 999:
            expected_qty = val
            found_qty = True

    # Look for tabular numbers adjacent to 'Articles' or 'Pkgs' headers
    if not found_qty:
        for i, line in enumerate(extracted_lines):
            if re.fullmatch(r'(?:No\.?\s*of\s*)?Articles?|Pkgs?|Packages?', line.strip(), re.IGNORECASE):
                for offset in [1, -1, 2]:
                    if 0 <= i + offset < len(extracted_lines):
                        cand_token = extracted_lines[i + offset].strip()
                        if cand_token.isdigit() and 1 <= int(cand_token) <= 500:
                            expected_qty = int(cand_token)
                            found_qty = True
                            break
                if found_qty:
                    break

    return {
        "lr_number": lr_number,
        "transport_name": transport_name,
        "sender_name": sender_name,
        "booking_date": booking_date,
        "expected_qty": expected_qty,
        "raw_text": full_text
    }