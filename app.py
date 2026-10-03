import streamlit as st
import pandas as pd
import os
import io
import shutil
from datetime import datetime
from src.data_handler import (
    init_db, add_consignment, get_records, mark_received, 
    generate_pdf_report, generate_transport_pdf_report,
    get_all_senders, add_sender, delete_sender,
    get_consignment_by_lr, update_consignment, delete_consignment,
    get_current_pin, update_pin, USE_SUPABASE, supabase_error_msg
)
from src.ocr_engine import extract_lr_details
from src.delay_monitor import get_delayed_shipments

st.set_page_config(page_title="Inward Logistics & LR Hub", layout="wide", page_icon="🚚")
init_db()

# ----------------- SIDEBAR STATUS (Visible Before Login) -----------------
with st.sidebar:
    st.write("### 🌐 System Status")
    if USE_SUPABASE:
        st.success("🟢 Connected to Cloud Database (Supabase)")
    else:
        st.error(f"🔴 Supabase Failed: {supabase_error_msg}")
    st.write("---")

# ----------------- AUTHENTICATION -----------------
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
        if st.button("Unlock Portal", width="stretch"):
            if pin_input == get_current_pin():
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Incorrect 6-digit PIN. Please try again.")
    return False

if not check_password():
    st.stop()

# ----------------- AUTHENTICATED SIDEBAR CONTROLS -----------------
with st.sidebar:
    st.write("### ⚙️ Security Settings")
    with st.expander("Change 6-Digit PIN"):
        curr_p = st.text_input("Current PIN", type="password", max_chars=6)
        new_p = st.text_input("New 6-Digit PIN", type="password", max_chars=6)
        conf_p = st.text_input("Confirm New PIN", type="password", max_chars=6)
        
        if st.button("Update PIN", width="stretch"):
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
    if st.button("🚪 Logout", width="stretch"):
        st.session_state.authenticated = False
        st.rerun()

# ----------------- METRICS -----------------
st.title("🚚 Local Inward Goods & LR Management System")

records = get_records()
delayed = get_delayed_shipments(records)
total_count = len(records)
in_transit_count = len(records[records['status'] == 'In Transit']) if not records.empty else 0
received_count = len(records[records['status'] == 'Received']) if not records.empty else 0
delayed_count = len(delayed) if not delayed.empty else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Consignments", total_count)
m2.metric("In Transit", in_transit_count)
m3.metric("Received at Godown", received_count)
m4.metric("Delayed (>21 Days)", delayed_count)
st.write("")

tabs = st.tabs([
    "📥 Intake Consignment", 
    "🏬 Godown Arrival", 
    "🚨 Monitoring & Pipeline", 
    "✏️ Edit & Manage Records", 
    "🏢 Manage Senders", 
    "💾 Export & Backup"
])

# =========================================================
# TAB 1: INTAKE CONSIGNMENT (Direct Entry / OCR)
# =========================================================
with tabs[0]:
    st.subheader("New Consignment Intake")
    
    if "intake_data" not in st.session_state:
        st.session_state.intake_data = {
            "lr_number": "", "transport_name": "SHIV SHANKAR",
            "sender_name": "", "booking_date": datetime.today().strftime('%d-%m-%Y'),
            "expected_qty": 1
        }

    uploaded_file = st.file_uploader("Drop LR Image (JPG/PNG)", type=["png", "jpg", "jpeg"], key="intake_uploader")
    
    if uploaded_file and st.session_state.get("last_uploaded") != uploaded_file.name:
        with st.spinner("Analyzing receipt with Gemini Vision..."):
            extracted = extract_lr_details(uploaded_file)
            st.session_state.intake_data.update(extracted)
            st.session_state.last_uploaded = uploaded_file.name
        st.success("Receipt scanned successfully!")

    senders_list = get_all_senders()
    cur_sender = st.session_state.intake_data.get("sender_name", "")
    sender_idx = senders_list.index(cur_sender) if cur_sender in senders_list else 0

    with st.form("consignment_form"):
        c1, c2 = st.columns(2)
        with c1:
            lr_no = st.text_input("LR Number *", value=st.session_state.intake_data["lr_number"])
            if senders_list:
                sender = st.selectbox("Sender Company Name *", options=senders_list, index=sender_idx)
            else:
                sender = st.text_input("Sender Company Name *", value=cur_sender)
            transport = st.text_input("Transport Company", value=st.session_state.intake_data["transport_name"] or "SHIV SHANKAR")
        with c2:
            bill_no = st.text_input("Bill Number (Optional)")
            b_date = st.text_input("Booking Date (DD-MM-YYYY)", value=st.session_state.intake_data["booking_date"])
            qty = st.number_input("Quantity of Packages/Articles", min_value=1, value=int(st.session_state.intake_data["expected_qty"]))

        if st.form_submit_button("Save Consignment", width="stretch"):
            clean_lr = lr_no.strip().upper()
            if not clean_lr:
                st.warning("LR Number is required.")
            elif not sender or not sender.strip():
                st.warning("Sender name is required.")
            elif get_consignment_by_lr(clean_lr):
                st.error(f"⚠️ LR '{clean_lr}' is already registered in the system!")
            else:
                add_consignment({
                    "lr_number": clean_lr,
                    "sender_name": sender.strip(),
                    "transport_name": transport.strip() if transport else "SHIV SHANKAR",
                    "bill_number": bill_no.strip(),
                    "booking_date": b_date.strip(),
                    "expected_qty": int(qty)
                })
                st.success(f"LR {clean_lr} registered successfully!")
                st.session_state.intake_data = {
                    "lr_number": "", "transport_name": "SHIV SHANKAR",
                    "sender_name": "", "booking_date": datetime.today().strftime('%d-%m-%Y'),
                    "expected_qty": 1
                }
                st.rerun()

# =========================================================
# TAB 2: GODOWN ARRIVAL
# =========================================================
with tabs[1]:
    st.subheader("Godown Arrival Check-In")
    search_lr = st.text_input("Enter LR Number to Check-In").strip().upper()
    
    if search_lr:
        record = get_consignment_by_lr(search_lr)
        if record:
            st.info(f"**Sender:** {record['sender_name']} | **Transport:** {record['transport_name']} | **Booking Date:** {record['booking_date']} | **Expected:** {record['expected_qty']}")
            if record['status'] != 'Received':
                with st.form("arrival_form"):
                    rcvd_qty = st.number_input("Actual Received Quantity", min_value=0, value=int(record['expected_qty']))
                    rcvd_date = st.date_input("Arrival Date", value=datetime.today())
                    if st.form_submit_button("Confirm Arrival", width="stretch"):
                        mark_received(search_lr, rcvd_qty, str(rcvd_date.strftime('%d-%m-%Y')))
                        st.success(f"LR {search_lr} marked as Received!")
                        st.rerun()
            else:
                st.success(f"✅ Already Received on {record['received_date']} (Quantity: {record['received_qty']})")
        else:
            st.warning(f"No consignment found with LR Number: {search_lr}")

# =========================================================
# TAB 3: MONITORING & PIPELINE
# =========================================================
with tabs[2]:
    st.subheader("Consignment Pipeline & Search")
    
    if not delayed.empty:
        st.error(f"🚨 Delay Alert: {len(delayed)} consignments delayed in transit for over 21 days!")
        st.dataframe(delayed[['lr_number', 'booking_date', 'days_in_transit', 'sender_name', 'transport_name', 'expected_qty', 'status']], width="stretch", hide_index=True)
    else:
        st.success("✅ All consignments are within expected delivery windows (<21 days).")

    st.write("---")
    st.write("#### Search Inward Records")
    
    q1, q2 = st.columns([2, 1])
    with q1:
        search_query = st.text_input("Filter by LR Number, Sender, or Transport").strip().lower()
    with q2:
        status_filter = st.selectbox("Filter Status", ["All", "In Transit", "Received"])

    filtered_df = records.copy()
    if status_filter != "All" and not filtered_df.empty:
        filtered_df = filtered_df[filtered_df['status'] == status_filter]

    if search_query and not filtered_df.empty:
        match = (
            filtered_df['lr_number'].astype(str).str.lower().str.contains(search_query) |
            filtered_df['sender_name'].astype(str).str.lower().str.contains(search_query) |
            filtered_df['transport_name'].astype(str).str.lower().str.contains(search_query)
        )
        filtered_df = filtered_df[match]

    st.dataframe(filtered_df, width="stretch", hide_index=True)

# =========================================================
# TAB 4: EDIT & DELETE RECORDS
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

                    if st.form_submit_button("Update Consignment", width="stretch"):
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
                    st.success(f"LR {lookup_lr} deleted permanently.")
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
        new_sender = st.text_input("New Company Name")
        if st.button("Save Sender", width="stretch"):
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
            if st.button(f"Delete '{to_delete}'", type="primary", width="stretch"):
                delete_sender(to_delete)
                st.success(f"Removed '{to_delete}' from sender directory.")
                st.rerun()
        else:
            st.info("No senders registered.")

    st.write("---")
    st.write("#### Registered Sender Companies")
    st.dataframe(pd.DataFrame(get_all_senders(), columns=["Registered Companies"]), width="stretch", hide_index=True)

# =========================================================
# TAB 6: EXPORT & BACKUP (Multi-Transport & Status Filters)
# =========================================================
with tabs[5]:
    st.subheader("Reports & Archive Exports")
    
    # Available transport companies for multi-selection
    available_transports = []
    if not records.empty and 'transport_name' in records.columns:
        available_transports = sorted([str(t) for t in records['transport_name'].dropna().unique() if str(t).strip()])

    # Global Filter Controls for Exports
    st.markdown("##### ⚙️ Export Filter Options")
    flt_col1, flt_col2 = st.columns(2)
    with flt_col1:
        sel_status = st.selectbox("Filter Consignments by Status", ["All", "In Transit", "Received"], key="exp_status")
    with flt_col2:
        sel_transports = st.multiselect(
            "Filter by Transport Company (Select One, Multiple, or Leave Empty for All)",
            options=available_transports,
            default=[],
            help="Leave blank to include all transports, or pick one or more specific companies."
        )

    # Helper function to generate filtered dataframe for Excel
    def get_export_df(is_transport_copy=False):
        df_exp = records.copy()
        if not df_exp.empty:
            if sel_status != "All":
                df_exp = df_exp[df_exp['status'] == sel_status]
            if sel_transports:
                upper_chosen = [str(t).upper() for t in sel_transports]
                df_exp = df_exp[df_exp['transport_name'].astype(str).str.upper().isin(upper_chosen)]
            if is_transport_copy:
                df_exp = df_exp.drop(columns=['sender_name'], errors='ignore')
        return df_exp

    trans_suffix = f"_{len(sel_transports)}_transports" if sel_transports else "_all_transports"
    status_suffix = sel_status.lower().replace(" ", "_")

    st.write("---")

    # 1. Standard Reports
    st.markdown("#### 🏢 Standard Reports (Includes Sender Company Names)")
    col_ex, col_pdf, col_zip = st.columns(3)

    with col_ex:
        st.write("##### Excel Sheet")
        buf_full = io.BytesIO()
        df_standard_excel = get_export_df(is_transport_copy=False)
        with pd.ExcelWriter(buf_full, engine='openpyxl') as writer:
            df_standard_excel.to_excel(writer, index=False, sheet_name="Full Report")
        st.download_button(
            label=f"📥 Download Full Excel ({sel_status})",
            data=buf_full.getvalue(),
            file_name=f"goods_{status_suffix}{trans_suffix}_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch"
        )

    with col_pdf:
        st.write("##### PDF Summary")
        full_pdf_bytes = generate_pdf_report(filter_status=sel_status, selected_transports=sel_transports)
        st.download_button(
            label=f"📥 Download Full PDF ({sel_status})",
            data=full_pdf_bytes,
            file_name=f"goods_{status_suffix}{trans_suffix}_{datetime.now().strftime('%d_%m_%Y')}.pdf",
            mime="application/pdf",
            width="stretch"
        )

    with col_zip:
        st.write("##### Local System Backup")
        if st.button("Generate System Backup ZIP", width="stretch"):
            shutil.make_archive("goods_backup", 'zip', "data")
            st.success("Backup archive refreshed!")
        if os.path.exists("goods_backup.zip"):
            with open("goods_backup.zip", "rb") as fp:
                st.download_button(
                    label="📥 Download System ZIP",
                    data=fp,
                    file_name="goods_backup.zip",
                    mime="application/zip",
                    width="stretch"
                )

    st.write("---")

    # 2. Transport & Driver Copies
    st.markdown("#### 🚚 Transport & Driver Copies (Without Sender Names)")
    st.caption("For external gate passes and transport offices without exposing sender company names.")

    col_t_pdf, col_t_ex = st.columns(2)

    with col_t_pdf:
        st.write("##### Transport PDF Report")
        trans_pdf_bytes = generate_transport_pdf_report(filter_status=sel_status, selected_transports=sel_transports)
        st.download_button(
            label=f"📥 Download Transport PDF ({sel_status})",
            data=trans_pdf_bytes,
            file_name=f"transport_{status_suffix}{trans_suffix}_{datetime.now().strftime('%d_%m_%Y')}.pdf",
            mime="application/pdf",
            width="stretch"
        )

    with col_t_ex:
        st.write("##### Transport Excel Manifest")
        buf_trans = io.BytesIO()
        df_trans_excel = get_export_df(is_transport_copy=True)
        with pd.ExcelWriter(buf_trans, engine='openpyxl') as writer:
            df_trans_excel.to_excel(writer, index=False, sheet_name="Transport Manifest")
        st.download_button(
            label=f"📥 Download Transport Excel ({sel_status})",
            data=buf_trans.getvalue(),
            file_name=f"transport_manifest_{status_suffix}{trans_suffix}_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch"
        )