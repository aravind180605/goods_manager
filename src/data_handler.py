import os
import io
import pandas as pd
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import streamlit as st

# Determine if Supabase credentials are configured
# --- SUPABASE CONNECTION INITIALIZATION ---
USE_SUPABASE = False
supabase = None
supabase_error_msg = ""

try:
    # 1. Check if secrets exist in Streamlit
    if not hasattr(st, "secrets"):
        supabase_error_msg = "st.secrets is not available."
    elif "SUPABASE_URL" not in st.secrets:
        supabase_error_msg = "SUPABASE_URL missing from Streamlit Secrets."
    elif "SUPABASE_KEY" not in st.secrets:
        supabase_error_msg = "SUPABASE_KEY missing from Streamlit Secrets."
    else:
        # 2. Import and test connection
        from supabase import create_client
        url = str(st.secrets["SUPABASE_URL"]).strip().strip('"').strip("'")
        key = str(st.secrets["SUPABASE_KEY"]).strip().strip('"').strip("'")
        
        supabase = create_client(url, key)
        # Test query to confirm live connection
        test_ping = supabase.table("app_settings").select("key").limit(1).execute()
        USE_SUPABASE = True
except Exception as err:
    USE_SUPABASE = False
    supabase_error_msg = str(err)

# Local SQLite fallback
import sqlite3
DB_PATH = os.path.join("data", "goods.db")
EXCEL_PATH = os.path.join("data", "goods_records.xlsx")

def _get_local_connection():
    return sqlite3.connect(DB_PATH, timeout=20.0)

def init_db():
    """Initializes local SQLite schema when running offline."""
    if USE_SUPABASE:
        return

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
        try:
            res = supabase.table("app_settings").select("value").eq("key", "security_pin").execute()
            if res.data:
                return res.data[0]["value"]
        except Exception as e:
            st.error(f"Error fetching PIN from Supabase: {e}")

    with _get_local_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM app_settings WHERE key = 'security_pin'")
        row = c.fetchone()
        return row[0] if row else "123456"

def update_pin(new_pin):
    if len(new_pin) == 6 and new_pin.isdigit():
        if USE_SUPABASE:
            try:
                supabase.table("app_settings").upsert({"key": "security_pin", "value": new_pin}).execute()
                return True, "PIN updated successfully in Supabase!"
            except Exception as e:
                return False, f"Supabase update error: {e}"

        with _get_local_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE app_settings SET value = ? WHERE key = 'security_pin'", (new_pin,))
            conn.commit()
        return True, "PIN updated successfully!"
    return False, "PIN must be exactly 6 numeric digits."

# --- SENDER OPERATIONS ---

def get_all_senders():
    if USE_SUPABASE:
        try:
            res = supabase.table("senders").select("sender_name").order("sender_name", desc=False).execute()
            return [row["sender_name"] for row in res.data if row.get("sender_name")]
        except Exception as e:
            st.error(f"Error loading senders from Supabase: {e}")

    with _get_local_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT sender_name FROM senders ORDER BY sender_name ASC")
        return [row[0] for row in c.fetchall()]

def add_sender(sender_name):
    name = str(sender_name).strip().upper()
    if not name:
        return False, "Sender name cannot be empty."

    if USE_SUPABASE:
        try:
            check = supabase.table("senders").select("id").eq("sender_name", name).execute()
            if check.data:
                return False, f"Sender '{name}' already exists in your records!"
            supabase.table("senders").insert({"sender_name": name}).execute()
            return True, f"Sender '{name}' added successfully!"
        except Exception as e:
            return False, f"Supabase error: {e}"

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
        try:
            supabase.table("senders").delete().eq("sender_name", name).execute()
            return True
        except Exception as e:
            st.error(f"Error deleting sender from Supabase: {e}")
            return False

    with _get_local_connection() as conn:
        conn.execute("DELETE FROM senders WHERE UPPER(TRIM(sender_name)) = ?", (name,))
        conn.commit()
    return True

# --- CONSIGNMENT CRUD OPERATIONS ---

def get_consignment_by_lr(lr_number):
    clean_lr = str(lr_number).strip().upper()
    if USE_SUPABASE:
        try:
            res = supabase.table("consignments").select("*").eq("lr_number", clean_lr).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            st.error(f"Error retrieving LR from Supabase: {e}")

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
        "transport_name": str(data.get('transport_name', 'SHIV SHANKAR')).strip().upper(),
        "bill_number": str(data.get('bill_number', '')).strip(),
        "booking_date": str(data.get('booking_date', '')).strip(),
        "expected_qty": int(data.get('expected_qty', 1)),
        "status": "In Transit",
        "received_qty": 0,
        "received_date": ""
    }

    if USE_SUPABASE:
        try:
            supabase.table("consignments").upsert(payload, on_conflict="lr_number").execute()
            return
        except Exception as e:
            st.error(f"Error saving consignment to Supabase: {e}")

    with _get_local_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO consignments 
            (lr_number, sender_name, transport_name, bill_number, booking_date, expected_qty, status, received_qty, received_date)
            VALUES (?, ?, ?, ?, ?, ?, 'In Transit', 0, '')
        """, (payload["lr_number"], payload["sender_name"], payload["transport_name"], 
              payload["bill_number"], payload["booking_date"], payload["expected_qty"]))
        conn.commit()

def update_consignment(data):
    clean_lr = str(data['lr_number']).strip().upper()
    payload = {
        "sender_name": str(data['sender_name']).strip().upper(),
        "transport_name": str(data.get('transport_name', 'SHIV SHANKAR')).strip().upper(),
        "bill_number": str(data.get('bill_number', '')).strip(),
        "booking_date": str(data.get('booking_date', '')).strip(),
        "expected_qty": int(data.get('expected_qty', 1)),
        "received_qty": int(data.get('received_qty', 0)),
        "received_date": str(data.get('received_date', '')).strip(),
        "status": str(data.get('status', 'In Transit')).strip()
    }

    if USE_SUPABASE:
        try:
            supabase.table("consignments").update(payload).eq("lr_number", clean_lr).execute()
            return
        except Exception as e:
            st.error(f"Error updating Supabase record: {e}")

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
        try:
            supabase.table("consignments").delete().eq("lr_number", clean_lr).execute()
            return
        except Exception as e:
            st.error(f"Error deleting record from Supabase: {e}")

    with _get_local_connection() as conn:
        conn.execute("DELETE FROM consignments WHERE UPPER(TRIM(lr_number)) = ?", (clean_lr,))
        conn.commit()

def get_records():
    columns = ['lr_number', 'sender_name', 'transport_name', 'bill_number', 'booking_date', 'expected_qty', 'received_qty', 'received_date', 'status']
    if USE_SUPABASE:
        try:
            res = supabase.table("consignments").select("*").execute()
            if res.data:
                return pd.DataFrame(res.data)
            return pd.DataFrame(columns=columns)
        except Exception as e:
            st.error(f"Error reading records from Supabase: {e}")

    with _get_local_connection() as conn:
        return pd.read_sql_query("SELECT * FROM consignments", conn)

def mark_received(lr_number, received_qty, received_date):
    clean_lr = str(lr_number).strip().upper()
    if USE_SUPABASE:
        try:
            supabase.table("consignments").update({
                "received_qty": int(received_qty),
                "received_date": str(received_date),
                "status": "Received"
            }).eq("lr_number", clean_lr).execute()
            return
        except Exception as e:
            st.error(f"Error updating status in Supabase: {e}")

    with _get_local_connection() as conn:
        conn.execute("""
            UPDATE consignments 
            SET received_qty = ?, received_date = ?, status = 'Received'
            WHERE UPPER(TRIM(lr_number)) = ?
        """, (int(received_qty), str(received_date), clean_lr))
        conn.commit()

# --- PDF GENERATION ---

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
    elements.append(Paragraph("<b>Local Goods & LR Tracking Report (Full)</b>", styles['Title']))
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

def generate_transport_pdf_report():
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
    elements.append(Paragraph("<b>Transport Delivery & Gate-Pass Report</b>", styles['Title']))
    elements.append(Spacer(1, 15))

    columns = ['LR Number', 'Transport', 'Booking Date', 'Expected', 'Received', 'Status']
    df_subset = df[['lr_number', 'transport_name', 'booking_date', 'expected_qty', 'received_qty', 'status']] if not df.empty else pd.DataFrame(columns=columns)
    
    table_data = [columns] + df_subset.values.tolist()
    t = Table(table_data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F766E')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0FDFA')])
    ]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()