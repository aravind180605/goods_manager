import os
import io
import pandas as pd
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import streamlit as st

# Attempt Supabase client initialization
USE_SUPABASE = False
supabase = None

try:
    if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets and "SUPABASE_KEY" in st.secrets:
        from supabase import create_client
        supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
        USE_SUPABASE = True
except Exception:
    USE_SUPABASE = False

# Local SQLite Fallback Setup
import sqlite3
DB_PATH = os.path.join("data", "goods.db")
EXCEL_PATH = os.path.join("data", "goods_records.xlsx")

def _get_local_connection():
    return sqlite3.connect(DB_PATH, timeout=20.0)

def init_db():
    if USE_SUPABASE:
        # Tables and seeds are created in Supabase SQL editor
        return
    
    # Offline fallback
    os.makedirs("data", exist_ok=True)
    with _get_local_connection() as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS consignments (
                lr_number TEXT PRIMARY KEY,
                sender_name TEXT,
                transport_name TEXT,
                bill_number TEXT,
                booking_date TEXT,
                expected_qty INTEGER,
                received_qty INTEGER DEFAULT 0,
                received_date TEXT DEFAULT '',
                status TEXT DEFAULT 'In Transit'
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS senders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_name TEXT UNIQUE NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        c.execute("SELECT COUNT(*) FROM senders")
        if c.fetchone()[0] == 0:
            c.executemany("INSERT OR IGNORE INTO senders (sender_name) VALUES (?)", 
                           [('OKK',), ('LALIT BHAI',), ('SHREE NIVASH BHAI',)])
        c.execute("SELECT value FROM app_settings WHERE key = 'security_pin'")
        if not c.fetchone():
            c.execute("INSERT INTO app_settings (key, value) VALUES ('security_pin', '123456')")
        conn.commit()

# --- SECURITY PIN OPERATIONS ---

def get_current_pin():
    if USE_SUPABASE:
        res = supabase.table("app_settings").select("value").eq("key", "security_pin").execute()
        return res.data[0]["value"] if res.data else "123456"

    with _get_local_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM app_settings WHERE key = 'security_pin'")
        row = c.fetchone()
        return row[0] if row else "123456"

def update_pin(new_pin):
    if len(new_pin) == 6 and new_pin.isdigit():
        if USE_SUPABASE:
            supabase.table("app_settings").update({"value": new_pin}).eq("key", "security_pin").execute()
            return True, "PIN updated successfully!"

        with _get_local_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE app_settings SET value = ? WHERE key = 'security_pin'", (new_pin,))
            conn.commit()
        return True, "PIN updated successfully!"
    return False, "PIN must be exactly 6 numeric digits."

# --- SENDER OPERATIONS ---

def get_all_senders():
    if USE_SUPABASE:
        res = supabase.table("senders").select("sender_name").order("sender_name", desc=False).execute()
        return [row["sender_name"] for row in res.data]

    with _get_local_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT sender_name FROM senders ORDER BY sender_name ASC")
        return [row[0] for row in c.fetchall()]

def add_sender(sender_name):
    name = str(sender_name).strip().upper()
    if not name:
        return False, "Sender name cannot be empty."

    if USE_SUPABASE:
        check = supabase.table("senders").select("id").eq("sender_name", name).execute()
        if check.data:
            return False, f"Sender '{name}' already exists in your records!"
        supabase.table("senders").insert({"sender_name": name}).execute()
        return True, f"Sender '{name}' added successfully!"

    with _get_local_connection() as conn:
        try:
            conn.execute("INSERT INTO senders (sender_name) VALUES (?)", (name,))
            conn.commit()
            return True, f"Sender '{name}' added successfully!"
        except sqlite3.IntegrityError:
            return False, f"Sender '{name}' already exists in your records!"

def delete_sender(sender_name):
    name = str(sender_name).strip().upper()
    if USE_SUPABASE:
        supabase.table("senders").delete().eq("sender_name", name).execute()
        return True

    with _get_local_connection() as conn:
        conn.execute("DELETE FROM senders WHERE UPPER(TRIM(sender_name)) = ?", (name,))
        conn.commit()
    return True

# --- CONSIGNMENT CRUD OPERATIONS ---

def get_consignment_by_lr(lr_number):
    clean_lr = str(lr_number).strip().upper()
    if USE_SUPABASE:
        res = supabase.table("consignments").select("*").eq("lr_number", clean_lr).execute()
        return res.data[0] if res.data else None

    with _get_local_connection() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM consignments WHERE UPPER(TRIM(lr_number)) = ?", (clean_lr,))
        row = c.fetchone()
        return dict(row) if row else None

def add_consignment(data):
    payload = {
        "lr_number": str(data['lr_number']).strip().upper(),
        "sender_name": str(data['sender_name']).strip().upper(),
        "transport_name": str(data['transport_name']).strip().upper(),
        "bill_number": str(data['bill_number']).strip(),
        "booking_date": str(data['booking_date']).strip(),
        "expected_qty": int(data['expected_qty']),
        "status": "In Transit",
        "received_qty": 0,
        "received_date": ""
    }

    if USE_SUPABASE:
        supabase.table("consignments").insert(payload).execute()
        return

    with _get_local_connection() as conn:
        conn.execute("""
            INSERT INTO consignments 
            (lr_number, sender_name, transport_name, bill_number, booking_date, expected_qty, status)
            VALUES (?, ?, ?, ?, ?, ?, 'In Transit')
        """, (payload["lr_number"], payload["sender_name"], payload["transport_name"], 
              payload["bill_number"], payload["booking_date"], payload["expected_qty"]))
        conn.commit()

def update_consignment(data):
    clean_lr = str(data['lr_number']).strip().upper()
    payload = {
        "sender_name": str(data['sender_name']).strip().upper(),
        "transport_name": str(data['transport_name']).strip().upper(),
        "bill_number": str(data['bill_number']).strip(),
        "booking_date": str(data['booking_date']).strip(),
        "expected_qty": int(data['expected_qty']),
        "received_qty": int(data['received_qty']),
        "received_date": str(data.get('received_date', '')).strip(),
        "status": str(data['status']).strip()
    }

    if USE_SUPABASE:
        supabase.table("consignments").update(payload).eq("lr_number", clean_lr).execute()
        return

    with _get_local_connection() as conn:
        conn.execute("""
            UPDATE consignments 
            SET sender_name = ?, transport_name = ?, bill_number = ?, booking_date = ?, 
                expected_qty = ?, received_qty = ?, received_date = ?, status = ?
            WHERE UPPER(TRIM(lr_number)) = ?
        """, (payload["sender_name"], payload["transport_name"], payload["bill_number"],
              payload["booking_date"], payload["expected_qty"], payload["received_qty"],
              payload["received_date"], payload["status"], clean_lr))
        conn.commit()

def delete_consignment(lr_number):
    clean_lr = str(lr_number).strip().upper()
    if USE_SUPABASE:
        supabase.table("consignments").delete().eq("lr_number", clean_lr).execute()
        return

    with _get_local_connection() as conn:
        conn.execute("DELETE FROM consignments WHERE UPPER(TRIM(lr_number)) = ?", (clean_lr,))
        conn.commit()

def get_records():
    columns = ['lr_number', 'sender_name', 'transport_name', 'bill_number', 'booking_date', 'expected_qty', 'received_qty', 'received_date', 'status']
    if USE_SUPABASE:
        res = supabase.table("consignments").select("*").execute()
        if res.data:
            return pd.DataFrame(res.data)
        return pd.DataFrame(columns=columns)

    with _get_local_connection() as conn:
        return pd.read_sql_query("SELECT * FROM consignments", conn)

def mark_received(lr_number, received_qty, received_date):
    clean_lr = str(lr_number).strip().upper()
    if USE_SUPABASE:
        supabase.table("consignments").update({
            "received_qty": int(received_qty),
            "received_date": str(received_date),
            "status": "Received"
        }).eq("lr_number", clean_lr).execute()
        return

    with _get_local_connection() as conn:
        conn.execute("""
            UPDATE consignments 
            SET received_qty = ?, received_date = ?, status = 'Received'
            WHERE UPPER(TRIM(lr_number)) = ?
        """, (int(received_qty), str(received_date), clean_lr))
        conn.commit()

def generate_pdf_report():
    df = get_records()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(letter), 
        rightMargin=30, 
        leftMargin=30, 
        topMargin=30, 
        bottomMargin=30
    )
    elements = []
    styles = getSampleStyleSheet()
    elements.append(Paragraph("<b>Local Goods & LR Tracking Report</b>", styles['Title']))
    elements.append(Spacer(1, 15))

    columns = ['LR Number', 'Sender', 'Transport', 'Booking Date', 'Expected', 'Received', 'Status']
    df_subset = df[['lr_number', 'sender_name', 'transport_name', 'booking_date', 'expected_qty', 'received_qty', 'status']] if not df.empty else pd.DataFrame(columns=columns)
    
    table_data = [columns] + df_subset.values.tolist()
    t = Table(table_data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')])
    ]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()