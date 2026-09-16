import sqlite3
import pandas as pd
import os
import io
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

DB_PATH = os.path.join("data", "goods.db")
EXCEL_PATH = os.path.join("data", "goods_records.xlsx")

def init_db():
    os.makedirs("data", exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        # Table 1: Consignments
        conn.execute("""
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
        # Table 2: Pre-defined Senders
        conn.execute("""
            CREATE TABLE IF NOT EXISTS senders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_name TEXT UNIQUE NOT NULL
            )
        """)
        # Table 3: App Security Settings
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        cursor = conn.cursor()
        # Seed default senders if empty
        cursor.execute("SELECT COUNT(*) FROM senders")
        if cursor.fetchone()[0] == 0:
            default_senders = [('OKK',), ('LALIT BHAI',), ('SHREE NIVASH BHAI',)]
            cursor.executemany("INSERT OR IGNORE INTO senders (sender_name) VALUES (?)", default_senders)

        # Seed default 6-digit PIN if missing
        cursor.execute("SELECT value FROM app_settings WHERE key = 'security_pin'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO app_settings (key, value) VALUES ('security_pin', '123456')")
            
        conn.commit()

# --- SECURITY PIN OPERATIONS ---

def get_current_pin():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = 'security_pin'")
        row = cursor.fetchone()
        return row[0] if row else "123456"

def update_pin(new_pin):
    if len(new_pin) == 6 and new_pin.isdigit():
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE app_settings SET value = ? WHERE key = 'security_pin'", (new_pin,))
            conn.commit()
        return True, "PIN updated successfully!"
    return False, "PIN must be exactly 6 numeric digits."

# --- SENDER OPERATIONS ---

def get_all_senders():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sender_name FROM senders ORDER BY sender_name ASC")
        return [row[0] for row in cursor.fetchall()]

def add_sender(sender_name):
    name = sender_name.strip().upper()
    if not name:
        return False, "Sender name cannot be empty."
    with sqlite3.connect(DB_PATH) as conn:
        try:
            conn.execute("INSERT INTO senders (sender_name) VALUES (?)", (name,))
            conn.commit()
            return True, f"Sender '{name}' added successfully!"
        except sqlite3.IntegrityError:
            return False, f"Sender '{name}' already exists in your records!"

def delete_sender(sender_name):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM senders WHERE sender_name = ?", (sender_name,))
        conn.commit()
    return True

# --- CONSIGNMENT CRUD OPERATIONS ---

def get_consignment_by_lr(lr_number):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM consignments WHERE lr_number = ?", (lr_number.strip(),))
        row = cursor.fetchone()
        if row:
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))
    return None

def add_consignment(data):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO consignments 
            (lr_number, sender_name, transport_name, bill_number, booking_date, expected_qty, status)
            VALUES (?, ?, ?, ?, ?, ?, 'In Transit')
        """, (
            data['lr_number'], data['sender_name'], data['transport_name'], 
            data['bill_number'], data['booking_date'], data['expected_qty']
        ))
    export_to_excel()

def update_consignment(data):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            UPDATE consignments 
            SET sender_name = ?, transport_name = ?, bill_number = ?, booking_date = ?, 
                expected_qty = ?, received_qty = ?, received_date = ?, status = ?
            WHERE lr_number = ?
        """, (
            data['sender_name'], data['transport_name'], data['bill_number'], data['booking_date'],
            data['expected_qty'], data['received_qty'], data['received_date'], data['status'],
            data['lr_number']
        ))
    export_to_excel()

def delete_consignment(lr_number):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM consignments WHERE lr_number = ?", (lr_number,))
        conn.commit()
    export_to_excel()

def get_records():
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query("SELECT * FROM consignments", conn)

def mark_received(lr_number, received_qty, received_date):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            UPDATE consignments 
            SET received_qty = ?, received_date = ?, status = 'Received'
            WHERE lr_number = ?
        """, (received_qty, received_date, lr_number))
    export_to_excel()

def export_to_excel():
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query("SELECT * FROM consignments", conn)
        df.to_excel(EXCEL_PATH, index=False)

# --- EXPORT TO PDF ---

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
    return buffer