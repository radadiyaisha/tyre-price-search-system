import streamlit as st
import pandas as pd
from datetime import datetime
from json_manager import JSONManager
from company_manager import CompanyManager

class Dashboard:
    def __init__(self):
        self.json_manager = JSONManager()
        self.company_manager = CompanyManager()

    def render(self):
        st.markdown("<h2 style='text-align: center; margin-bottom: 30px;'>Tyre Price Dashboard</h2>", unsafe_allow_html=True)

        # 1. Load data
        metadata = self.json_manager.get_pdf_metadata()
        all_companies = self.company_manager.get_all_companies()
        
        # Calculate Metrics
        total_companies = len(set(m["company"] for m in metadata))
        total_pdfs = len(metadata)
        total_records = sum(m["record_count"] for m in metadata)
        
        last_upload_str = "N/A"
        if metadata:
            last_upload = metadata[0]["upload_date"]
            try:
                dt = datetime.fromisoformat(last_upload)
                last_upload_str = dt.strftime("%d-%b-%Y %I:%M %p")
            except Exception:
                last_upload_str = str(last_upload)[:16]

        # 2. Render Metrics Row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(label="Active Companies", value=total_companies, delta=f"Out of {len(all_companies)} registered")
        with col2:
            st.metric(label="Uploaded PDFs", value=total_pdfs)
        with col3:
            st.metric(label="Extracted Records", value=total_records)
        with col4:
            st.metric(label="Last Upload Date", value=last_upload_str.split(" ")[0] if last_upload_str != "N/A" else "N/A", help=last_upload_str)

        st.markdown("---")

        if not metadata:
            st.info("No tyre price lists have been uploaded yet. Go to **Upload PDF** in the sidebar to get started.")
            return

        # 3. Visualizations Row
        st.subheader("Price List Distribution")
        
        # Build DataFrame for charts
        df = pd.DataFrame(metadata)
        
        col_chart, col_table = st.columns([1, 1])
        
        with col_chart:
            st.markdown("##### Records per Tyre Company")
            company_counts = df.groupby("company")["record_count"].sum().reset_index()
            # Rename columns for st.bar_chart index
            company_counts = company_counts.set_index("company")
            st.bar_chart(company_counts)

        with col_table:
            st.markdown("##### Records per Price List")
            pdf_counts = df[["pdf_name", "company", "record_count"]].rename(columns={
                "pdf_name": "PDF File",
                "company": "Company",
                "record_count": "Records"
            })
            st.dataframe(pdf_counts, width="stretch", hide_index=True)

        st.markdown("---")

        # 4. Uploaded Files Audit Log
        st.subheader("Uploaded Files Registry")
        audit_data = []
        for m in metadata:
            try:
                dt = datetime.fromisoformat(m["upload_date"])
                dt_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                dt_str = m["upload_date"]
                
            audit_data.append({
                "Company": m["company"],
                "PDF File Name": m["pdf_name"],
                "Processed Date": dt_str,
                "Records Extracted": m["record_count"]
            })
            
        st.dataframe(pd.DataFrame(audit_data), width="stretch", hide_index=True)
