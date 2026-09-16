import re
import streamlit as st
from paddleocr import PaddleOCR

@st.cache_resource(show_spinner=False)
def load_ocr_model():
    """Caches the PaddleOCR engine in memory so it doesn't reload on every interaction."""
    return PaddleOCR(use_angle_cls=True, lang='en', show_log=False)

def extract_lr_details(file_path):
    ocr = load_ocr_model()
    result = ocr.ocr(file_path, cls=True)
    
    extracted_lines = []
    if result and result[0]:
        for line in result[0]:
            text = line[1][0].strip()
            extracted_lines.append(text)

    full_text = "\n".join(extracted_lines)
    
    transport_name = "SHIV SHANKAR"

    # 1. Extract LR Number (K + Prefix + Digits, e.g. KRJKT04612, KSHPR00411)
    lr_number = ""
    lr_code_match = re.search(r'\b(K[A-Z]{3,5}\d{4,7})\b', full_text, re.IGNORECASE)
    if lr_code_match:
        lr_number = lr_code_match.group(1).upper()
    else:
        for i, line in enumerate(extracted_lines):
            clean = re.sub(r'[^A-Za-z0-9]', '', line).upper()
            if "LRNO" in clean:
                for offset in [1, 2, -1]:
                    if 0 <= i + offset < len(extracted_lines):
                        cand = re.sub(r'[^A-Za-z0-9]', '', extracted_lines[i + offset]).upper()
                        if cand not in ["REMARKS", "ROUTE", "GSTIN", "CONSIGNEE"] and len(cand) >= 6:
                            lr_number = cand
                            break
                if lr_number:
                    break

    # 2. Extract Booking Date
    booking_date = ""
    date_match = re.search(r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})', full_text)
    if date_match:
        booking_date = date_match.group(1).replace('/', '-')

    # 3. Extract Consigner
    sender_name = ""
    known_senders = re.search(r'\b(OOK|OKK|0KK|LALIT\s*BHAI|SHREE\s*NIVASH)\b', full_text, re.IGNORECASE)
    if known_senders:
        sender_name = known_senders.group(1).upper()
    else:
        for i, line in enumerate(extracted_lines):
            if re.search(r'Consi[gq]ner', line, re.IGNORECASE):
                for offset in range(1, 4):
                    if i + offset < len(extracted_lines):
                        cand = extracted_lines[i + offset].strip()
                        if not re.search(r'(Booking|Consignee|Description|Articles|Route|GSTIN|:)', cand, re.IGNORECASE):
                            sender_name = cand
                            break
                if sender_name:
                    break

    if sender_name in ["OOK", "0KK", "O0K", "O.K.K"]:
        sender_name = "OKK"

    # 4. Extract Articles (Quantity)
    expected_qty = 1
    for i, line in enumerate(extracted_lines):
        if re.fullmatch(r'Articles?', line.strip(), re.IGNORECASE):
            for offset in [1, -1, 2, -2]:
                if 0 <= i + offset < len(extracted_lines):
                    token = extracted_lines[i + offset].strip()
                    if token.isdigit() and 1 <= int(token) <= 500:
                        expected_qty = int(token)
                        break
            if expected_qty != 1:
                break

    if expected_qty == 1:
        qty_pattern = re.search(r'\b(\d{1,3})\s*(?:BUNDLES|BAGS|BOXES|CARTONS|CTNS|PKTS)\b', full_text, re.IGNORECASE)
        if qty_pattern:
            expected_qty = int(qty_pattern.group(1))

    return {
        "lr_number": lr_number,
        "transport_name": transport_name,
        "sender_name": sender_name,
        "booking_date": booking_date,
        "expected_qty": expected_qty,
        "raw_text": full_text
    }