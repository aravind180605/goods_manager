import sqlite3
import os
import pandas as pd
from datetime import datetime
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import io

DB_PATH = os.path.join("data", "goods.db")
EXCEL_PATH = os.path.join("data", "goods_records.xlsx")

def get_connection():
    """Returns a thread-safe connection with a busy timeout."""
    return sqlite3.connect(DB_PATH, timeout=20.0)

def init_db():
    os.makedirs("data", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)
    
    with get_connection() as conn:
        c = conn.cursor()
        
        # 1. Consignments Table
        c.execute("""
            CREATE TABLE IF NOT EXISTS consignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lr_number TEXT UNIQUE,
                sender_name TEXT,
                transport_name TEXT,
                bill_number TEXT,
                booking_date TEXT,
                expected_qty INTEGER,
                received_qty INTEGER DEFAULT 0,
                status TEXT DEFAULT 'In Transit',
                received_date TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. Senders Table
        c.execute("""
            CREATE TABLE IF NOT EXISTS senders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_name TEXT UNIQUE NOT NULL
            )
        """)
        
        # Senders Migration: Ensure 'sender_name' exists if table previously had 'name'
        c.execute("PRAGMA table_info(senders)")
        cols = [row[1] for row in c.fetchall()]
        if "sender_name" not in cols and "name" in cols:
            try:
                c.execute("ALTER TABLE senders RENAME COLUMN name TO sender_name")
            except Exception:
                c.execute("ALTER TABLE senders ADD COLUMN sender_name TEXT")
                c.execute("UPDATE senders SET sender_name = name")
        
        # Seed default senders if empty
        c.execute("SELECT COUNT(*) FROM senders")
        if c.fetchone()[0] == 0:
            default_senders = [('OKK',), ('LALIT BHAI',), ('SHREE NIVASH BHAI',)]
            c.executemany("INSERT OR IGNORE INTO senders (sender_name) VALUES (?)", default_senders)

        # 3. Settings Table
        c.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        c.execute("SELECT value FROM app_settings WHERE key = 'security_pin'")
        if not c.fetchone():
            c.execute("INSERT INTO app_settings (key, value) VALUES ('security_pin', '123456')")
            
        conn.commit()

# --- SECURITY PIN OPERATIONS ---

def get_current_pin():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM app_settings WHERE key = 'security_pin'")
        row = c.fetchone()
        return row[0] if row else "123456"

def update_pin(new_pin):
    if len(new_pin) == 6 and new_pin.isdigit():
        with get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE app_settings SET value = ? WHERE key = 'security_pin'", (new_pin,))
            conn.commit()
        return True, "PIN updated successfully!"
    return False, "PIN must be exactly 6 numeric digits."

# --- SENDER OPERATIONS ---

def _get_sender_column_name(conn):
    c = conn.cursor()
    c.execute("PRAGMA table_info(senders)")
    cols = [row[1] for row in c.fetchall()]
    return "sender_name" if "sender_name" in cols else "name"

def get_all_senders():
    with get_connection() as conn:
        col = _get_sender_column_name(conn)
        c = conn.cursor()
        c.execute(f"SELECT {col} FROM senders WHERE {col} IS NOT NULL AND TRIM({col}) != '' ORDER BY {col} ASC")
        return [row[0] for row in c.fetchall()]

def add_sender(sender_name):
    name = str(sender_name).strip().upper()
    if not name:
        return False, "Sender name cannot be empty."
    with get_connection() as conn:
        col = _get_sender_column_name(conn)
        try:
            conn.execute(f"INSERT INTO senders ({col}) VALUES (?)", (name,))
            conn.commit()
            return True, f"Sender '{name}' added successfully!"
        except sqlite3.IntegrityError:
            return False, f"Sender '{name}' already exists in your records!"

def delete_sender(sender_name):
    name = str(sender_name).strip().upper()
    with get_connection() as conn:
        col = _get_sender_column_name(conn)
        conn.execute(f"DELETE FROM senders WHERE UPPER(TRIM({col})) = ?", (name,))
        conn.commit()
    return True

# --- CONSIGNMENT OPERATIONS ---

def get_consignment_by_lr(lr_number):
    clean_lr = str(lr_number).strip().upper()
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM consignments WHERE UPPER(TRIM(lr_number)) = ?", (clean_lr,))
        row = c.fetchone()
        if row:
            return dict(row)
    return None

def add_consignment(data):
    clean_lr = str(data['lr_number']).strip().upper()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO consignments 
            (lr_number, sender_name, transport_name, bill_number, booking_date, expected_qty, status)
            VALUES (?, ?, ?, ?, ?, ?, 'In Transit')
        """, (
            clean_lr, str(data['sender_name']).strip().upper(), 
            str(data['transport_name']).strip().upper(), 
            str(data['bill_number']).strip(), str(data['booking_date']).strip(), 
            int(data['expected_qty'])
        ))
        conn.commit()
    export_to_excel()

def update_consignment(data):
    clean_lr = str(data['lr_number']).strip().upper()
    with get_connection() as conn:
        conn.execute("""
            UPDATE consignments 
            SET sender_name = ?, transport_name = ?, bill_number = ?, booking_date = ?, 
                expected_qty = ?, received_qty = ?, received_date = ?, status = ?
            WHERE UPPER(TRIM(lr_number)) = ?
        """, (
            str(data['sender_name']).strip().upper(),
            str(data['transport_name']).strip().upper(),
            str(data['bill_number']).strip(),
            str(data['booking_date']).strip(),
            int(data['expected_qty']),
            int(data['received_qty']),
            str(data.get('received_date', '')).strip(),
            str(data['status']).strip(),
            clean_lr
        ))
        conn.commit()
    export_to_excel()

def delete_consignment(lr_number):
    clean_lr = str(lr_number).strip().upper()
    with get_connection() as conn:
        conn.execute("DELETE FROM consignments WHERE UPPER(TRIM(lr_number)) = ?", (clean_lr,))
        conn.commit()
    export_to_excel()

def get_records():
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM consignments ORDER BY rowid DESC", conn)

def mark_received(lr_number, received_qty, received_date):
    clean_lr = str(lr_number).strip().upper()
    with get_connection() as conn:
        conn.execute("""
            UPDATE consignments 
            SET received_qty = ?, received_date = ?, status = 'Received'
            WHERE UPPER(TRIM(lr_number)) = ?
        """, (int(received_qty), str(received_date), clean_lr))
        conn.commit()
    export_to_excel()

def export_to_excel():
    with get_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM consignments", conn)
        df.to_excel(EXCEL_PATH, index=False)

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
    df_subset = df[['lr_number', 'sender_name', 'transport_name', 'booking_date', 'expected_qty', 'received_qty', 'status']]
    
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