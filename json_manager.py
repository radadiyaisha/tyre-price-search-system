import os
import json
from datetime import datetime
from utils import get_dir, logger

class JSONManager:
    def __init__(self):
        self.json_dir = get_dir("json_data")
        self.uploads_dir = get_dir("uploads")

    def _get_company_dir(self, company):
        """Helper to get and create company-specific JSON directory."""
        path = os.path.join(self.json_dir, company)
        os.makedirs(path, exist_ok=True)
        return path

    def save_pdf_records(self, company, pdf_name, records):
        """
        Saves a list of records extracted from a PDF file.
        Records list schema:
        [
            {
                "company": str,
                "pdf_name": str,
                "tyre_size": str,
                "headers": list,
                "row": dict
            },
            ...
        ]
        """
        company_dir = self._get_company_dir(company)
        # Replace characters that might be invalid in filenames
        clean_pdf_name = os.path.basename(pdf_name)
        json_filename = f"{os.path.splitext(clean_pdf_name)[0]}.json"
        json_path = os.path.join(company_dir, json_filename)

        payload = {
            "company": company,
            "pdf_name": clean_pdf_name,
            "upload_date": datetime.now().isoformat(),
            "records": records
        }

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4, ensure_ascii=False)
            logger.info(f"Successfully saved {len(records)} records for {company} - {clean_pdf_name} to JSON.")
            return True
        except Exception as e:
            logger.error(f"Failed to save records to JSON at {json_path}: {e}")
            return False

    def get_pdf_metadata(self):
        """
        Scans all JSON files and returns a list of dictionaries with metadata
        about all uploaded/processed price lists.
        """
        metadata_list = []
        if not os.path.exists(self.json_dir):
            return metadata_list

        for item in os.listdir(self.json_dir):
            item_path = os.path.join(self.json_dir, item)
            # Check if it's a company directory
            if os.path.isdir(item_path):
                company = item
                for file in os.listdir(item_path):
                    if file.endswith(".json"):
                        file_path = os.path.join(item_path, file)
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                metadata_list.append({
                                    "company": company,
                                    "pdf_name": data.get("pdf_name", file),
                                    "upload_date": data.get("upload_date", ""),
                                    "record_count": len(data.get("records", [])),
                                    "file_path": file_path
                                })
                        except Exception as e:
                            logger.error(f"Error reading metadata from {file_path}: {e}")
        return sorted(metadata_list, key=lambda x: x["upload_date"], reverse=True)

    def load_all_records(self):
        """
        Loads and returns all records from all stored JSON files.
        """
        all_records = []
        if not os.path.exists(self.json_dir):
            return all_records

        for item in os.listdir(self.json_dir):
            item_path = os.path.join(self.json_dir, item)
            if os.path.isdir(item_path):
                for file in os.listdir(item_path):
                    if file.endswith(".json"):
                        file_path = os.path.join(item_path, file)
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                # Attach upload_date to records if not present
                                upload_date = data.get("upload_date", "")
                                for rec in data.get("records", []):
                                    rec["upload_date"] = upload_date
                                    all_records.append(rec)
                        except Exception as e:
                            logger.error(f"Error loading records from {file_path}: {e}")
        return all_records

    def delete_pdf(self, company, pdf_name):
        """
        Deletes the structured JSON file and its raw uploaded PDF counterpart.
        """
        # Delete JSON
        clean_pdf_name = os.path.basename(pdf_name)
        json_filename = f"{os.path.splitext(clean_pdf_name)[0]}.json"
        json_path = os.path.join(self.json_dir, company, json_filename)
        
        deleted_json = False
        if os.path.exists(json_path):
            try:
                os.remove(json_path)
                logger.info(f"Deleted JSON file: {json_path}")
                deleted_json = True
            except Exception as e:
                logger.error(f"Failed to delete JSON file {json_path}: {e}")
        
        # Check if the company folder is now empty, delete if so
        company_dir = os.path.join(self.json_dir, company)
        if os.path.exists(company_dir) and not os.listdir(company_dir):
            try:
                os.rmdir(company_dir)
                logger.info(f"Deleted empty company directory: {company_dir}")
            except Exception as e:
                logger.error(f"Failed to delete company directory {company_dir}: {e}")

        # Delete raw upload PDF
        raw_pdf_path = os.path.join(self.uploads_dir, clean_pdf_name)
        deleted_raw = False
        if os.path.exists(raw_pdf_path):
            try:
                os.remove(raw_pdf_path)
                logger.info(f"Deleted raw uploaded file: {raw_pdf_path}")
                deleted_raw = True
            except Exception as e:
                logger.error(f"Failed to delete raw file {raw_pdf_path}: {e}")

        return deleted_json or deleted_raw

    def delete_all(self):
        """
        Deletes all JSON record files, empty company folders, and raw uploaded PDFs.
        Preserves companies.json.
        """
        # Delete all files in uploads
        for file in os.listdir(self.uploads_dir):
            file_path = os.path.join(self.uploads_dir, file)
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"Error removing raw file {file_path}: {e}")

        # Delete all subdirectories/files in json_data, except companies.json
        for item in os.listdir(self.json_dir):
            if item == "companies.json":
                continue
            item_path = os.path.join(self.json_dir, item)
            try:
                if os.path.isdir(item_path):
                    # Delete files in folder
                    for subfile in os.listdir(item_path):
                        os.remove(os.path.join(item_path, subfile))
                    os.rmdir(item_path)
                else:
                    os.remove(item_path)
            except Exception as e:
                logger.error(f"Error clearing item {item_path}: {e}")
        logger.info("All uploaded files and record JSONs have been deleted.")
        return True
