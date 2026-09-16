import streamlit as st
import pandas as pd
import os
import io
import shutil
from datetime import datetime
from src.data_handler import (
    init_db, add_consignment, get_records, mark_received, 
    generate_pdf_report, get_all_senders, add_sender, delete_sender,
    get_consignment_by_lr, update_consignment, delete_consignment,
    get_current_pin, update_pin
)
from src.ocr_engine import extract_lr_details
from src.delay_monitor import get_delayed_shipments

st.set_page_config(page_title="Inward Logistics & LR Hub", layout="wide", page_icon="🚚")

init_db()

# ----------------- 6-DIGIT APP ACCESS LOCK -----------------
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.markdown("<h2 style='text-align: center;'>🔒 Authorized Access Only</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Enter your 6-digit security PIN to access the portal.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        pin_input = st.text_input("Security PIN (6 Digits)", type="password", max_chars=6, placeholder="Default: 123456")
        if st.button("Unlock Portal", width='stretch'):
            current_pin = get_current_pin()
            if pin_input == current_pin:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Incorrect 6-digit PIN. Please try again.")
    return False

if not check_password():
    st.stop()

# ----------------- SIDEBAR CONTROLS -----------------
with st.sidebar:
    st.write("### ⚙️ Security Settings")
    with st.expander("Change 6-Digit PIN"):
        curr_p = st.text_input("Current PIN", type="password", max_chars=6)
        new_p = st.text_input("New 6-Digit PIN", type="password", max_chars=6)
        conf_p = st.text_input("Confirm New PIN", type="password", max_chars=6)
        
        if st.button("Update PIN", width='stretch'):
            if curr_p != get_current_pin():
                st.error("Current PIN is incorrect.")
            elif new_p != conf_p:
                st.error("New PINs do not match.")
            else:
                success, msg = update_pin(new_p)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
    
    st.write("---")
    if st.button("🚪 Logout", width='stretch'):
        st.session_state.authenticated = False
        st.rerun()

# ----------------- DASHBOARD METRICS -----------------
st.markdown("""
<style>
    .metric-card {
        background: #ffffff;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        border-left: 5px solid #1E3A8A;
        text-align: center;
    }
    .metric-title { color: #64748B; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; }
    .metric-value { color: #0F172A; font-size: 1.8rem; font-weight: 700; margin-top: 5px; }
</style>
""", unsafe_allow_html=True)

st.title("🚚 Local Inward Goods & LR Management System")

records = get_records()
delayed = get_delayed_shipments(records)
total_count = len(records)
in_transit_count = len(records[records['status'] == 'In Transit']) if not records.empty else 0
received_count = len(records[records['status'] == 'Received']) if not records.empty else 0
delayed_count = len(delayed) if not delayed.empty else 0

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown(f'<div class="metric-card"><div class="metric-title">Total Consignments</div><div class="metric-value">{total_count}</div></div>', unsafe_allow_html=True)
with m2:
    st.markdown(f'<div class="metric-card"><div class="metric-title">In Transit</div><div class="metric-value">{in_transit_count}</div></div>', unsafe_allow_html=True)
with m3:
    st.markdown(f'<div class="metric-card"><div class="metric-title">Received at Godown</div><div class="metric-value" style="color:#059669;">{received_count}</div></div>', unsafe_allow_html=True)
with m4:
    st.markdown(f'<div class="metric-card"><div class="metric-title">Delayed (>21 Days)</div><div class="metric-value" style="color:#DC2626;">{delayed_count}</div></div>', unsafe_allow_html=True)

st.write("")

tabs = st.tabs([
    "📥 Intake Consignment", 
    "🏬 Godown Arrival", 
    "🚨 Monitoring & Pipeline", 
    "✏️ Edit & Manage Records", 
    "🏢 Manage Senders", 
    "💾 Export & Backup"
])

# Initialize session state tracking
if "scan_lr" not in st.session_state:
    st.session_state.scan_lr = ""
if "scan_sender" not in st.session_state:
    st.session_state.scan_sender = ""
if "scan_transport" not in st.session_state:
    st.session_state.scan_transport = ""
if "scan_date" not in st.session_state:
    st.session_state.scan_date = datetime.today().strftime('%d-%m-%Y')
if "scan_qty" not in st.session_state:
    st.session_state.scan_qty = 1
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "last_processed_file" not in st.session_state:
    st.session_state.last_processed_file = None

# =========================================================
# TAB 1: INTAKE CONSIGNMENT (High Speed Vision AI)
# =========================================================
with tabs[0]:
    st.subheader("New Consignment Intake")
    
    uploaded_file = st.file_uploader(
        "Upload or Capture LR Receipt", 
        type=["png", "jpg", "jpeg", "webp"], 
        key=f"lr_uploader_{st.session_state.uploader_key}"
    )
    
    if uploaded_file is not None and st.session_state.last_processed_file != uploaded_file.name:
        os.makedirs("uploads", exist_ok=True)
        file_path = os.path.join("uploads", uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        with st.spinner("⚡ Quick analyzing receipt..."):
            ext = extract_lr_details(file_path)
            st.session_state.scan_lr = ext.get("lr_number", "")
            st.session_state.scan_transport = ext.get("transport_name", "")
            st.session_state.scan_sender = ext.get("sender_name", "")
            st.session_state.scan_date = ext.get("booking_date", datetime.today().strftime('%d-%m-%Y'))
            st.session_state.scan_qty = int(ext.get("expected_qty", 1))
            st.session_state.last_processed_file = uploaded_file.name
            
            if st.session_state.scan_sender:
                existing = get_all_senders()
                if st.session_state.scan_sender not in existing:
                    add_sender(st.session_state.scan_sender)
            st.rerun()

    senders_list = get_all_senders()
    if not senders_list:
        senders_list = ["OKK", "LALIT BHAI", "SHREE NIVASH", "PRITHVI SUITING"]
        for s in senders_list:
            add_sender(s)

    sender_options = list(senders_list) + ["+ Enter New / Other Sender"]
    default_sender_idx = 0
    if st.session_state.scan_sender in sender_options:
        default_sender_idx = sender_options.index(st.session_state.scan_sender)

    with st.form("intake_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            lr_no = st.text_input("LR Number *", value=st.session_state.scan_lr)
            selected_sender_opt = st.selectbox(
                "Sender Company Name (Consigner) *", 
                options=sender_options, 
                index=default_sender_idx
            )
            
            custom_sender = ""
            if selected_sender_opt == "+ Enter New / Other Sender":
                custom_sender = st.text_input("Type New Sender Name *", value=st.session_state.scan_sender)
                
            transport = st.text_input("Goods/Transport Company", value=st.session_state.scan_transport)
            
        with c2:
            bill_no = st.text_input("Bill Number (Optional)")
            b_date = st.text_input("Booking Date (DD-MM-YYYY)", value=st.session_state.scan_date)
            qty = st.number_input("Quantity of Articles/Cartons/Thaan *", min_value=1, value=int(st.session_state.scan_qty))

        submitted = st.form_submit_button("Save Consignment", width='stretch')
        
        if submitted:
            clean_lr = lr_no.strip().upper()
            chosen_sender = custom_sender.strip().upper() if selected_sender_opt == "+ Enter New / Other Sender" else selected_sender_opt.strip().upper()

            if not clean_lr:
                st.warning("LR Number is required.")
            elif not chosen_sender:
                st.warning("Sender Company Name is required.")
            else:
                existing_record = get_consignment_by_lr(clean_lr)
                if existing_record:
                    st.error(f"⚠️ DUPLICATE FOUND: LR Number '{clean_lr}' is already registered in the system!")
                    st.json(existing_record)
                else:
                    if chosen_sender not in senders_list:
                        add_sender(chosen_sender)

                    add_consignment({
                        "lr_number": clean_lr,
                        "sender_name": chosen_sender,
                        "transport_name": transport.strip().upper() if transport else "DIRECT",
                        "bill_number": bill_no.strip() if bill_no else "",
                        "booking_date": b_date.strip(),
                        "expected_qty": int(qty)
                    })
                    st.success(f"Consignment LR {clean_lr} registered successfully!")
                    
                    # Reset state and clear uploader widget
                    st.session_state.scan_lr = ""
                    st.session_state.scan_sender = ""
                    st.session_state.scan_transport = ""
                    st.session_state.scan_date = datetime.today().strftime('%d-%m-%Y')
                    st.session_state.scan_qty = 1
                    st.session_state.last_processed_file = None
                    st.session_state.uploader_key += 1
                    st.rerun()

# =========================================================
# TAB 2: GODOWN ARRIVAL CHECK-IN
# =========================================================
with tabs[1]:
    st.subheader("Godown Arrival Check-In")
    search_lr = st.text_input("Scan or Enter LR Number to Check-In").strip().upper()
    
    if search_lr:
        record = get_consignment_by_lr(search_lr)
        if record:
            st.markdown(f"""
            **Sender:** {record['sender_name']} &nbsp;|&nbsp; 
            **Transport:** {record['transport_name']} &nbsp;|&nbsp; 
            **Booking Date:** {record['booking_date']} &nbsp;|&nbsp; 
            **Expected Quantity:** {record['expected_qty']}
            """)
            
            if record['status'] != 'Received':
                with st.form("arrival_form"):
                    rcvd_qty = st.number_input("Actual Received Quantity", min_value=0, value=int(record['expected_qty']))
                    rcvd_date = st.date_input("Arrival Date", value=datetime.today())
                    
                    if st.form_submit_button("Confirm Godown Arrival", width='stretch'):
                        mark_received(search_lr, rcvd_qty, str(rcvd_date.strftime('%d-%m-%Y')))
                        st.success(f"LR {search_lr} marked as Received!")
                        st.rerun()
            else:
                st.info(f"✅ Already Received on {record['received_date']} (Actual Qty: {record['received_qty']})")
        else:
            st.warning(f"No consignment found with LR Number: {search_lr}")

# =========================================================
# TAB 3: MONITORING & PIPELINE
# =========================================================
with tabs[2]:
    st.subheader("Consignment Pipeline & Delay Monitoring")
    
    if not delayed.empty:
        st.error(f"🚨 Delay Alert: {len(delayed)} consignments delayed in transit for over 21 days!")
        disp_cols = ['lr_number', 'booking_date', 'days_in_transit', 'sender_name', 'transport_name', 'expected_qty', 'status']
        st.dataframe(
            delayed[disp_cols].rename(columns={
                'lr_number': 'LR Number',
                'booking_date': 'Booking Date',
                'days_in_transit': 'Days Delayed',
                'sender_name': 'Sender Name',
                'transport_name': 'Transport',
                'expected_qty': 'Qty',
                'status': 'Status'
            }),
            width='stretch',
            hide_index=True
        )
    else:
        st.success("✅ All pending consignments are currently within transit windows (<21 days).")

    st.write("---")
    st.write("### 🔍 Search & Filter Pipeline")
    
    sc1, sc2, sc3 = st.columns([2, 1, 1])
    with sc1:
        query = st.text_input("Search LR, Sender, Transport, or Bill No", placeholder="Type keyword...").strip().lower()
    with sc2:
        status_filter = st.selectbox("Status", ["All", "In Transit", "Received"])
    with sc3:
        sort_by = st.selectbox("Sort", ["Latest Added", "Oldest Added"])

    filtered_df = records.copy()
    if not filtered_df.empty:
        if status_filter != "All":
            filtered_df = filtered_df[filtered_df['status'] == status_filter]
        
        if query:
            filtered_df = filtered_df[
                filtered_df['lr_number'].astype(str).str.lower().str.contains(query) |
                filtered_df['sender_name'].astype(str).str.lower().str.contains(query) |
                filtered_df['transport_name'].astype(str).str.lower().str.contains(query) |
                filtered_df['bill_number'].astype(str).str.lower().str.contains(query)
            ]
        
        if sort_by == "Latest Added":
            filtered_df = filtered_df.iloc[::-1]

    st.caption(f"Showing **{len(filtered_df)}** consignments")
    st.dataframe(filtered_df, width='stretch', hide_index=True)

# =========================================================
# TAB 4: EDIT & MANAGE RECORDS
# =========================================================
with tabs[3]:
    st.subheader("Edit or Delete Consignments")
    lookup_lr = st.text_input("Enter LR Number to Edit / Delete").strip().upper()
    if lookup_lr:
        target = get_consignment_by_lr(lookup_lr)
        if target:
            with st.expander("📝 Modify Consignment Details", expanded=True):
                with st.form("edit_form"):
                    e1, e2 = st.columns(2)
                    with e1:
                        edit_sender = st.text_input("Sender Name", value=target['sender_name'])
                        edit_transport = st.text_input("Transport Name", value=target['transport_name'])
                        edit_bill = st.text_input("Bill Number", value=target['bill_number'])
                    with e2:
                        edit_date = st.text_input("Booking Date", value=target['booking_date'])
                        edit_exp_qty = st.number_input("Expected Qty", min_value=1, value=int(target['expected_qty']))
                        edit_rcv_qty = st.number_input("Received Qty", min_value=0, value=int(target['received_qty']))
                        edit_status = st.selectbox("Status", ["In Transit", "Received"], index=0 if target['status'] == 'In Transit' else 1)
                        edit_rcv_date = st.text_input("Received Date", value=target['received_date'])

                    if st.form_submit_button("Update Consignment", width='stretch'):
                        update_consignment({
                            "lr_number": lookup_lr,
                            "sender_name": edit_sender,
                            "transport_name": edit_transport,
                            "bill_number": edit_bill,
                            "booking_date": edit_date,
                            "expected_qty": edit_exp_qty,
                            "received_qty": edit_rcv_qty,
                            "received_date": edit_rcv_date,
                            "status": edit_status
                        })
                        st.success(f"LR {lookup_lr} updated successfully!")
                        st.rerun()

            st.write("---")
            with st.expander("🗑️ Danger Zone: Delete Record"):
                st.warning(f"Are you sure you want to permanently delete LR '{lookup_lr}'?")
                if st.button(f"Yes, Delete {lookup_lr}", type="primary"):
                    delete_consignment(lookup_lr)
                    st.success(f"LR {lookup_lr} was deleted permanently.")
                    st.rerun()
        else:
            st.warning("Consignment not found.")

# =========================================================
# TAB 5: MANAGE SENDERS
# =========================================================
with tabs[4]:
    st.subheader("Manage Sender Directory")
    c_add, c_del = st.columns([1, 1])

    with c_add:
        st.write("#### Add Sender")
        new_sender = st.text_input("Enter New Company Name")
        if st.button("Save Sender", width='stretch'):
            success, msg = add_sender(new_sender)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with c_del:
        st.write("#### Delete Sender")
        all_senders = get_all_senders()
        if all_senders:
            to_delete = st.selectbox("Select Sender to Remove", options=all_senders)
            if st.button(f"Delete '{to_delete}'", type="primary", width='stretch'):
                delete_sender(to_delete)
                st.success(f"Removed '{to_delete}' from sender directory.")
                st.rerun()
        else:
            st.info("No senders registered.")

    st.write("---")
    st.write("#### Registered Sender Companies")
    st.dataframe(pd.DataFrame(get_all_senders(), columns=["Registered Companies"]), width='stretch', hide_index=True)

# =========================================================
# TAB 6: EXPORT & BACKUP
# =========================================================
with tabs[5]:
    st.subheader("Reports & Archive Exports")
    col_ex, col_pdf, col_zip = st.columns(3)

    with col_ex:
        st.write("### Excel Sheet")
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            records.to_excel(writer, index=False, sheet_name="Inward Goods")
        st.download_button(
            label="📥 Download Excel (.xlsx)",
            data=buf.getvalue(),
            file_name=f"goods_export_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch'
        )

    with col_pdf:
        st.write("### PDF Summary")
        pdf_bytes = generate_pdf_report()
        st.download_button(
            label="📥 Download PDF Report",
            data=pdf_bytes,
            file_name=f"goods_summary_{datetime.now().strftime('%d_%m_%Y')}.pdf",
            mime="application/pdf",
            width='stretch'
        )

    with col_zip:
        st.write("### Local Backup Archive")
        if st.button("Generate System Backup ZIP", width='stretch'):
            shutil.make_archive("goods_backup", 'zip', "data")
            st.success("Backup archive refreshed!")
        if os.path.exists("goods_backup.zip"):
            with open("goods_backup.zip", "rb") as fp:
                st.download_button(
                    label="📥 Download Full System ZIP",
                    data=fp,
                    file_name="goods_backup.zip",
                    mime="application/zip",
                    width='stretch'
                )