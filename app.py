import os
import streamlit as st
from datetime import datetime

# Initialize directories & logging first
from utils import get_dir, clean_temp_dir, logger
from company_manager import CompanyManager
from json_manager import JSONManager
from pdf_processor import PDFProcessor
from search_engine import SearchEngine
from dashboard import Dashboard
from ocr_processor import is_ocr_available, get_easyocr_reader

# Page configuration
st.set_page_config(
    page_title="Tyre Price Intelligence System",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium Styling Injection
st.markdown("""
    <style>
        /* Main page layout tweaks */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        
        /* Metric styling */
        div[data-testid="stMetricValue"] {
            font-size: 2.2rem;
            font-weight: 700;
            color: #ff4b4b;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 0.95rem;
            font-weight: 500;
        }
        
        /* Tyre Result Cards styling (Glassmorphism & Shadows) */
        .tyre-card {
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            background-color: #f9f9f9;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .tyre-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.1);
        }
        .dark-theme .tyre-card {
            border: 1px solid #464855;
            background-color: #1e1e24;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        
        .card-header {
            border-bottom: 2px solid #ff4b4b;
            padding-bottom: 8px;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .card-title {
            font-size: 1.25rem;
            font-weight: 700;
            color: #ff4b4b;
            margin: 0;
        }
        .card-meta {
            font-size: 0.85rem;
            color: #757575;
            font-style: italic;
        }
        
        /* Custom responsive grid */
        .data-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 12px;
        }
        .grid-item {
            padding: 8px 12px;
            background: rgba(0,0,0,0.02);
            border-radius: 4px;
            border-left: 3px solid #ccc;
        }
        .grid-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: #666;
            margin-bottom: 2px;
            font-weight: 600;
        }
        .grid-value {
            font-size: 0.95rem;
            font-weight: 700;
        }
        
        /* Quick tags */
        .tyre-tag {
            background-color: #ff4b4b;
            color: white;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 600;
        }
    </style>
""", unsafe_allow_html=True)

# Initialize System Classes
if 'company_mgr' not in st.session_state:
    st.session_state.company_mgr = CompanyManager()
if 'json_mgr' not in st.session_state:
    st.session_state.json_mgr = JSONManager()
if 'pdf_proc' not in st.session_state:
    st.session_state.pdf_proc = PDFProcessor()
if 'search_eng' not in st.session_state:
    st.session_state.search_eng = SearchEngine()

company_mgr = st.session_state.company_mgr
json_mgr = st.session_state.json_mgr
pdf_proc = st.session_state.pdf_proc
search_eng = st.session_state.search_eng

# App Title
st.sidebar.markdown("<h2 style='text-align: center; color: #ff4b4b;'>🚗 Tyre Price IQ</h2>", unsafe_allow_html=True)
st.sidebar.markdown("<p style='text-align: center; font-size:0.85em; margin-bottom: 25px;'>Intelligence System v1.0</p>", unsafe_allow_html=True)

# Sidebar Navigation
menu = st.sidebar.radio(
    "Navigation Menu",
    ["Dashboard", "Upload PDF",  "Search Tyres", "Manage PDFs",]
)

# -----------------
# 1. DASHBOARD PAGE
# -----------------
if menu == "Dashboard":
    dashboard = Dashboard()
    dashboard.render()

# -----------------
# 2. UPLOAD PDF PAGE
# -----------------
elif menu == "Upload PDF":
    st.title("📤 Upload Tyre Price Sheets")
    st.markdown("Upload tyre price lists in **PDF** or **Image** formats. The system will automatically parse structures, detect sizes, and build search indices.")

    companies = company_mgr.get_all_companies()
    
    col_c, col_info = st.columns([1, 2])
    with col_c:
        selected_company = st.selectbox("Select Tyre Company:", companies)
    # with col_info:
    #     st.info("💡 Don't see your brand? Go to the **Companies** tab in the sidebar to add a custom tyre brand instantly.")

    uploaded_files = st.file_uploader(
        "Choose PDF or Image files:",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    if uploaded_files:
        if st.button("Process & Index Uploads", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            uploads_dir = get_dir("uploads")
            success_count = 0
            
            for idx, uploaded_file in enumerate(uploaded_files):
                file_name = uploaded_file.name
                status_text.markdown(f"Saving and extracting **{file_name}**...")
                
                # Save uploaded file physically to uploads/
                file_path = os.path.join(uploads_dir, file_name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Process PDF/Image
                result = pdf_proc.process_pdf(file_path, selected_company)
                
                if result.get("success", False):
                    success_count += 1
                    st.success(f"✅ **{file_name}** parsed successfully via **{result['method']}**! Extracted **{result['record_count']}** tyre size records.")
                else:
                    st.error(f"❌ Failed to extract records from **{file_name}**. Check system logs for details.")
                
                # Update progress
                progress = (idx + 1) / len(uploaded_files)
                progress_bar.progress(progress)
            
            # Clear temporary artifacts & rebuild index
            clean_temp_dir()
            status_text.markdown("Rebuilding search engine index...")
            search_eng.rebuild_index()
            status_text.empty()
            progress_bar.empty()
            
            st.balloons()
            st.success(f"Processing completed! **{success_count}** of **{len(uploaded_files)}** documents successfully processed and indexed.")

# -----------------
# 3. SEARCH TYRES PAGE
# -----------------
elif menu == "Search Tyres":
    st.title("🔍 Search Tyre Prices")
    st.markdown("Instantly query extracted price lists across all uploaded PDFs. Supports both exact sizes and intelligent fuzzy typo correction.")

    # Search bar layout
    col_s1, col_s2 = st.columns([3, 1])
    with col_s1:
        query = st.text_input(
            "Enter Tyre Size:",
            placeholder="E.g., 145/80R12, 6.00-16, 295/80R22.5, 31X10.5R15...",
            help="Type standard, truck, decimal bias, flotation, or shorthand tyre size formats."
        )
    with col_s2:
        enable_fuzzy = st.checkbox("Enable Fuzzy Backup", value=True, help="Finds similar size suggestions if the exact size isn't located.")

    if query:
        # Search index
        results = search_eng.search(query, fuzzy=enable_fuzzy)
        
        exact = results.get("exact_matches", [])
        fuzzy = results.get("fuzzy_matches", [])
        
        # Display Results
        if exact:
            st.markdown(f"### 🎯 Exact Matches Found ({len(exact)})")
            
            for item in exact:
                company = item["company"]
                pdf_name = item["pdf_name"]
                tyre_size = item["tyre_size"]
                headers = item["headers"]
                row_data = item["row"]
                upload_date_raw = item.get("upload_date", "")
                
                # Format Date
                try:
                    dt = datetime.fromisoformat(upload_date_raw)
                    dt_str = dt.strftime("%d-%b-%Y")
                except Exception:
                    dt_str = "Unknown"

                # Card HTML Structure (Flat string with zero leading indentation to prevent markdown block parsing)
                card_html = '<div class="tyre-card">'
                card_html += f'<div style="margin-bottom: 8px; font-size: 1.05rem;"><b>Company</b> : {company}</div>'
                card_html += f'<div style="margin-bottom: 8px; font-size: 1.05rem;"><b>PDF</b> : {pdf_name}</div>'
                card_html += f'<div style="margin-bottom: 8px; font-size: 1.05rem;"><b>Upload Date</b> : {dt_str}</div>'
                card_html += '<div style="margin-top: 12px; margin-bottom: 12px; border-bottom: 1px solid #ff4b4b;"></div>'
                
                # Populate cells line by line
                for col in headers:
                    val = row_data.get(col, "N/A")
                    card_html += f'<div style="margin-bottom: 6px; font-size: 1.05rem;"><b>{col}</b> : {val}</div>'
                
                card_html += '</div>'
                st.markdown(card_html, unsafe_allow_html=True)
                
        elif fuzzy:
            st.markdown(f"### 🤔 No exact match. Did you mean? (Suggestions)")
            
            for hit in fuzzy:
                size_label = hit["size"]
                score = hit["score"]
                records = hit["records"]
                
                # Render an expandable card containing all matching records under this size suggestion
                with st.expander(f"📏 {size_label} — (Confidence Match: {score}%)"):
                    for item in records:
                        company = item["company"]
                        pdf_name = item["pdf_name"]
                        headers = item["headers"]
                        row_data = item["row"]
                        
                        # Card HTML Structure (Flat string with zero leading indentation to prevent markdown block parsing)
                        card_html = '<div class="tyre-card">'
                        card_html += f'<div style="margin-bottom: 8px; font-size: 1.05rem;"><b>Company</b> : {company}</div>'
                        card_html += f'<div style="margin-bottom: 8px; font-size: 1.05rem;"><b>PDF</b> : {pdf_name}</div>'
                        card_html += '<div style="margin-top: 12px; margin-bottom: 12px; border-bottom: 1px solid #ff4b4b;"></div>'
                        
                        # Populate cells line by line
                        for col in headers:
                            val = row_data.get(col, "N/A")
                            card_html += f'<div style="margin-bottom: 6px; font-size: 1.05rem;"><b>{col}</b> : {val}</div>'
                        
                        card_html += '</div>'
                        st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.warning(f"🔍 No exact or close fuzzy matches found for query: **{query}**.")
            st.info("💡 Tips: Verify the tyre size pattern format (e.g. check for slashes, dashes, or missing digits). Ensure you have uploaded the corresponding PDF price list.")

# -----------------
# 4. MANAGE PDFS PAGE
# -----------------
elif menu == "Manage PDFs":
    st.title("📂 Manage Price Lists")
    st.markdown("Overview and administrative tools for all processed tyre price sheets.")

    metadata = json_mgr.get_pdf_metadata()

    if not metadata:
        st.info("No tyre price list sheets found. Proceed to the **Upload PDF** section to import documents.")
    else:
        # Display list of PDFs with Action Buttons
        for idx, m in enumerate(metadata):
            company = m["company"]
            pdf_name = m["pdf_name"]
            count = m["record_count"]
            date_raw = m["upload_date"]
            
            try:
                dt = datetime.fromisoformat(date_raw)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_str = date_raw

            # Card structure for each PDF management actions
            with st.container(border=True):
                col_info, col_act = st.columns([3, 2])
                with col_info:
                    st.write(f"🏢 **Company:** {company}")
                    st.write(f"📄 **File:** {pdf_name}")
                    st.write(f"📅 **Date Processed:** {date_str} | 📈 **Extracted Records:** {count}")
                
                with col_act:
                    # Line of actions
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("🔄 Reprocess", key=f"reproc_{idx}"):
                            uploads_path = os.path.join(get_dir("uploads"), pdf_name)
                            if os.path.exists(uploads_path):
                                with st.spinner("Extracting..."):
                                    res = pdf_proc.process_pdf(uploads_path, company)
                                    if res.get("success", False):
                                        st.success(f"Reprocessed successfully! Extracted {res['record_count']} records.")
                                        search_eng.rebuild_index()
                                        st.rerun()
                                    else:
                                        st.error("Failed to reprocess file.")
                            else:
                                st.error("Raw source PDF file not found in uploads folder.")
                    with c2:
                        if st.button("🗑️ Delete", key=f"delete_{idx}"):
                            if json_mgr.delete_pdf(company, pdf_name):
                                st.success(f"Deleted {pdf_name} successfully.")
                                search_eng.rebuild_index()
                                st.rerun()
                            else:
                                st.error("Failed to delete records.")

        st.markdown("---")
        st.subheader("⚠️ Global Operations")
        
        c_all_del, c_all_reproc = st.columns(2)
        with c_all_del:
            if st.button("🔴 Purge All Extracted Data", type="secondary", width="stretch"):
                json_mgr.delete_all()
                search_eng.rebuild_index()
                st.success("Successfully deleted all files, folders, and index databases.")
                st.rerun()
        with c_all_reproc:
            if st.button("🔄 Reprocess All Uploaded PDFs", type="primary", width="stretch"):
                uploads_dir = get_dir("uploads")
                active_files = [f for f in os.listdir(uploads_dir) if os.path.isfile(os.path.join(uploads_dir, f))]
                
                if not active_files:
                    st.info("No raw uploaded PDFs found in workspace.")
                else:
                    # Rescan JSON metadata files to map files back to companies
                    file_to_company = {m["pdf_name"]: m["company"] for m in metadata}
                    
                    progress = st.progress(0)
                    for i, fname in enumerate(active_files):
                        comp = file_to_company.get(fname, "YOKOHAMA")  # fallback default
                        fpath = os.path.join(uploads_dir, fname)
                        pdf_proc.process_pdf(fpath, comp)
                        progress.progress((i + 1) / len(active_files))
                    
                    search_eng.rebuild_index()
                    st.success(f"Successfully reprocessed all {len(active_files)} documents.")
                    st.rerun()

# -----------------
# 6. SETTINGS PAGE
# -----------------
elif menu == "Settings":
    st.title("⚙️ System Diagnostics & Settings")
    st.markdown("Inspect local environment variables, OCR configurations, dependencies, and file log registers.")

    # OCR Diagnostics
    st.subheader("🔍 OCR Engine Status")
    ocr_status = "Available" if is_ocr_available() else "Unavailable (Mock Simulation Active)"
    
    if is_ocr_available():
        st.success(f"✅ **EasyOCR Status:** {ocr_status}")
    else:
        st.warning(f"⚠️ **EasyOCR Status:** {ocr_status}")
        st.markdown("""
            Since **PyTorch** and **EasyOCR** are massive machine learning libraries, they might not be installed by default or are still installing in the background.
            
            **How to install EasyOCR locally:**
            ```bash
            pip install torch torchvision
            pip install easyocr
            ```
            *The system will automatically switch from simulated fallback to active EasyOCR once imports resolve.*
        """)

    # Display raw logs
    st.subheader("📋 System Event Logs (`logs/app.log`)")
    log_path = os.path.join(get_dir("logs"), "app.log")
    
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                # Show last 40 lines
                logs_content = "".join(lines[-40:])
                st.code(logs_content, language="text")
        except Exception as e:
            st.error(f"Error reading log file: {e}")
    else:
        st.info("No log files registered yet.")

    # Storage Size
    st.subheader("💾 Workspace Data Summary")
    uploads_dir = get_dir("uploads")
    json_dir = get_dir("json_data")
    
    uploads_size = sum(os.path.getsize(os.path.join(uploads_dir, f)) for f in os.listdir(uploads_dir) if os.path.isfile(os.path.join(uploads_dir, f)))
    json_size = 0
    for root, dirs, files in os.walk(json_dir):
        for f in files:
            json_size += os.path.getsize(os.path.join(root, f))
            
    st.markdown(f"""
        - **Uploads Folder Size:** `{uploads_size / (1024*1024):.2f} MB`
        - **JSON Storage Folder Size:** `{json_size / 1024:.2f} KB`
        - **Total Searchable Entries:** `{len(search_eng.all_unique_sizes)} unique tyre sizes`
    """)
