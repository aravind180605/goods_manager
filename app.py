import streamlit as st
import pandas as pd
import os
import io
import shutil
from datetime import datetime
from src.data_handler import (
    init_db, add_consignment, get_records, mark_received, 
    generate_pdf_report, get_all_senders, add_sender, delete_sender,
    get_consignment_by_lr, update_consignment, delete_consignment
)
from src.ocr_engine import extract_lr_details
from src.delay_monitor import get_delayed_shipments

# Page Configuration
st.set_page_config(page_title="Inward Logistics & LR Hub", layout="wide", page_icon="🚚")
init_db()

# Custom UI Styling
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

# Application Header & Metrics Dashboard
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

# =========================================================
# TAB 1: INTAKE CONSIGNMENT (With Duplicate Detection)
# =========================================================
with tabs[0]:
    st.subheader("New Consignment Intake")
    uploaded_file = st.file_uploader("Drop LR Image (JPG/PNG)", type=["png", "jpg", "jpeg"])
    
    extracted = {
        "lr_number": "",
        "transport_name": "SHIV SHANKAR",
        "sender_name": "",
        "booking_date": datetime.today().strftime('%d-%m-%Y'),
        "expected_qty": 1
    }
    
    if uploaded_file:
        os.makedirs("uploads", exist_ok=True)
        file_path = os.path.join("uploads", uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        with st.spinner("Analyzing receipt with PaddleOCR..."):
            extracted = extract_lr_details(file_path)
        st.success("Receipt scanned successfully!")

    senders_list = get_all_senders()
    default_sender_idx = 0
    if extracted["sender_name"] and extracted["sender_name"] in senders_list:
        default_sender_idx = senders_list.index(extracted["sender_name"])

    with st.form("intake_form"):
        c1, c2 = st.columns(2)
        with c1:
            lr_no = st.text_input("LR Number *", value=extracted["lr_number"])
            if senders_list:
                sender = st.selectbox("Sender Company Name (Consigner) *", options=senders_list, index=default_sender_idx)
            else:
                sender = st.text_input("Sender Company Name (Consigner) *", value=extracted["sender_name"])
            transport = st.text_input("Goods/Transport Company", value=extracted["transport_name"])
        with c2:
            bill_no = st.text_input("Bill Number (Optional)")
            b_date = st.text_input("Booking Date (DD-MM-YYYY)", value=str(extracted["booking_date"]))
            qty = st.number_input("Quantity of Articles/Cartons", min_value=1, value=int(extracted["expected_qty"]) if extracted["expected_qty"] else 1)

        submitted = st.form_submit_button("Save Consignment", use_container_width=True)
        
        if submitted:
            clean_lr = lr_no.strip().upper()
            if not clean_lr:
                st.warning("LR Number is required.")
            else:
                existing_record = get_consignment_by_lr(clean_lr)
                if existing_record:
                    st.error(f"⚠️ DUPLICATE FOUND: LR Number '{clean_lr}' is already registered in the system!")
                    st.info("Here is the existing registered data:")
                    st.json(existing_record)
                else:
                    add_consignment({
                        "lr_number": clean_lr,
                        "sender_name": sender,
                        "transport_name": transport,
                        "bill_number": bill_no,
                        "booking_date": b_date,
                        "expected_qty": qty
                    })
                    st.success(f"LR {clean_lr} registered successfully!")
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
                    
                    if st.form_submit_button("Confirm Godown Arrival", use_container_width=True):
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

    st.write("### Complete Inward Pipeline")
    st.dataframe(records, width='stretch', hide_index=True)

# =========================================================
# TAB 4: EDIT & MANAGE RECORDS
# =========================================================
with tabs[3]:
    st.subheader("Edit or Delete Consignments")
    st.caption("Search an LR number to modify incorrect data or remove an entry completely.")
    
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

                    if st.form_submit_button("Update Consignment", use_container_width=True):
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
        if st.button("Save Sender", use_container_width=True):
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
            if st.button(f"Delete '{to_delete}'", type="primary", use_container_width=True):
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
            use_container_width=True
        )

    with col_pdf:
        st.write("### PDF Summary")
        pdf_bytes = generate_pdf_report()
        st.download_button(
            label="📥 Download PDF Report",
            data=pdf_bytes,
            file_name=f"goods_summary_{datetime.now().strftime('%d_%m_%Y')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    with col_zip:
        st.write("### Local Backup Archive")
        if st.button("Generate System Backup ZIP", use_container_width=True):
            shutil.make_archive("goods_backup", 'zip', "data")
            st.success("Backup archive refreshed!")
        if os.path.exists("goods_backup.zip"):
            with open("goods_backup.zip", "rb") as fp:
                st.download_button(
                    label="📥 Download Full System ZIP",
                    data=fp,
                    file_name="goods_backup.zip",
                    mime="application/zip",
                    use_container_width=True
                )