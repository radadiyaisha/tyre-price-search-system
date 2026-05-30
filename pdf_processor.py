import os
import pdfplumber
import fitz  # PyMuPDF
from utils import get_dir, logger
from size_detector import detect_tyre_sizes
from json_manager import JSONManager
from ocr_processor import convert_pdf_to_images, process_image_file, is_ocr_available

class PDFProcessor:
    def __init__(self):
        self.json_manager = JSONManager()

    def is_scanned_pdf(self, pdf_path):
        """
        Determines if a PDF is a scanned document by counting extracted text length.
        If character count across first few pages is very low (< 100), it's likely scanned.
        """
        try:
            doc = fitz.open(pdf_path)
            total_chars = 0
            # Check up to first 3 pages
            pages_to_check = min(3, len(doc))
            for i in range(pages_to_check):
                page = doc.load_page(i)
                total_chars += len(page.get_text().strip())
            
            doc.close()
            # If less than 100 characters total across pages, classify as scanned
            logger.info(f"PDF text character count: {total_chars}")
            return total_chars < 150
        except Exception as e:
            logger.error(f"Error checking if PDF is scanned {pdf_path}: {e}")
            return True # Treat as scanned on failure to be safe

    def clean_headers(self, raw_header_row):
        """
        Cleans header labels (removes newlines, trims spaces, handles duplicates or empty labels).
        """
        clean_headers = []
        seen = {}
        for idx, col in enumerate(raw_header_row):
            if col is None:
                col_name = f"Column_{idx+1}"
            else:
                col_name = str(col).replace("\n", " ").strip()
                if not col_name:
                    col_name = f"Column_{idx+1}"
            
            # De-duplicate column names
            if col_name in seen:
                seen[col_name] += 1
                col_name = f"{col_name}_{seen[col_name]}"
            else:
                seen[col_name] = 1
            
            clean_headers.append(col_name)
        return clean_headers

    def process_pdf(self, pdf_path, company):
        """
        Processes a PDF or Image file, extracts data using native parsing or OCR fallback,
        saves records to JSON, and returns a dictionary with processing results.
        """
        pdf_name = os.path.basename(pdf_path)
        logger.info(f"Starting processing for {pdf_name} (Company: {company})...")

        # 1. Check if the file is a direct image
        file_ext = os.path.splitext(pdf_path)[1].lower()
        if file_ext in [".png", ".jpg", ".jpeg"]:
            logger.info(f"{pdf_name} detected as raw image. Routing directly to OCR pipeline...")
            return self.process_image_ocr(pdf_path, company)

        # 2. Check if the PDF is scanned (image-based)
        if self.is_scanned_pdf(pdf_path):
            logger.info(f"{pdf_name} detected as scanned. Directing to OCR pipeline...")
            return self.process_scanned_pdf_ocr(pdf_path, company)

        # 2. Extract tables via pdfplumber
        records = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    if not tables:
                        # Sometimes text blocks have tabular layout but not solid gridlines
                        # Let's inspect the page words or try to see if any lines can be parsed
                        logger.warning(f"No gridlines table found on page {page_num + 1} of {pdf_name}. Try text parsing.")
                        text_records = self.extract_from_plain_text(page.extract_text(), company, pdf_name)
                        records.extend(text_records)
                        continue

                    for table_idx, table in enumerate(tables):
                        if not table or len(table) < 2:
                            continue
                        
                        # Detect the actual column header row dynamically.
                        # Spacer rows, category titles (like "12 Inch"), or logos have very few non-empty cells
                        # and miss key price-list labels. We scan the first few rows and score them.
                        header_row_idx = 0
                        best_score = -1
                        best_idx = 0
                        
                        header_keywords = [
                            "code", "size", "rim", "pattern", "mrp", "yrp", "price", "sku", 
                            "fitment", "vehicle", "tyre", "tube", "flap", "rate", "description", 
                            "invoice", "rcp", "best", "ss", "li"
                        ]
                        
                        # Inspect up to the first min(5, len(table)) rows
                        rows_to_check = min(5, len(table))
                        for r_idx in range(rows_to_check):
                            row = table[r_idx]
                            if not row:
                                continue
                            
                            # Count non-empty elements
                            non_empty_count = sum(1 for cell in row if cell is not None and str(cell).strip() != "")
                            
                            # Count keyword matches
                            keyword_matches = 0
                            for cell in row:
                                if cell is not None:
                                    cell_lower = str(cell).lower().strip()
                                    if any(kw in cell_lower for kw in header_keywords):
                                        keyword_matches += 1
                            
                            # Score calculation: density weight + matching keywords
                            score = non_empty_count + 5 * keyword_matches
                            
                            if score > best_score:
                                best_score = score
                                best_idx = r_idx
                                
                        header_row_idx = best_idx
                        raw_headers = table[header_row_idx]
                        headers = self.clean_headers(raw_headers)
                        
                        # Process data rows
                        for row in table[header_row_idx + 1:]:
                            if not row:
                                continue
                            
                            # Concatenate row cell values to look for tyre sizes
                            row_text = " ".join(str(cell) for cell in row if cell is not None)
                            
                            # Clean cell dictionary
                            row_dict = {}
                            for col_idx, cell in enumerate(row):
                                if col_idx < len(headers):
                                    cell_val = str(cell).replace("\n", " ").strip() if cell is not None else ""
                                    row_dict[headers[col_idx]] = cell_val

                            # Extract tyre sizes
                            tyre_sizes = detect_tyre_sizes(row_text)
                            if not tyre_sizes:
                                # Not a data row, skip
                                continue
                            
                            # Add record for each matched size
                            for size in tyre_sizes:
                                records.append({
                                    "company": company,
                                    "pdf_name": pdf_name,
                                    "tyre_size": size,
                                    "headers": headers,
                                    "row": row_dict
                                })

            # If no records were found using native table extractors, try OCR fallback as a backup
            if not records:
                logger.warning(f"Native parsing succeeded but extracted 0 records from {pdf_name}. Routing to OCR fallback.")
                return self.process_scanned_pdf_ocr(pdf_path, company)

            # Save extracted records to JSON
            success = self.json_manager.save_pdf_records(company, pdf_name, records)
            return {
                "success": success,
                "record_count": len(records),
                "method": "Native PDF Parser",
                "pdf_name": pdf_name,
                "company": company
            }

        except Exception as e:
            logger.error(f"Error during native PDF parsing of {pdf_path}: {e}. Routing to OCR fallback.")
            return self.process_scanned_pdf_ocr(pdf_path, company)

    def extract_from_plain_text(self, text, company, pdf_name):
        """
        Fallback parser when tables have no gridlines but text contains clear tyre lines.
        """
        records = []
        if not text:
            return records
            
        lines = text.split("\n")
        # Synthesize generic headers for text dumps
        headers = ["Line Content"]
        
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
                
            tyre_sizes = detect_tyre_sizes(line_str)
            if tyre_sizes:
                for size in tyre_sizes:
                    records.append({
                        "company": company,
                        "pdf_name": pdf_name,
                        "tyre_size": size,
                        "headers": headers,
                        "row": {"Line Content": line_str}
                    })
        return records

    def process_scanned_pdf_ocr(self, pdf_path, company):
        """
        Handles OCR table extraction by rendering pages to images and processing.
        """
        pdf_name = os.path.basename(pdf_path)
        
        # 1. Convert PDF pages to PNGs
        image_paths = convert_pdf_to_images(pdf_path)
        if not image_paths:
            logger.error(f"Failed to render pages for scanned PDF {pdf_name}")
            return {"success": False, "record_count": 0, "method": "OCR Engine (Failed Rendering)", "pdf_name": pdf_name, "company": company}

        # 2. Extract table records from each page
        records = []
        ocr_active = is_ocr_available()
        method_str = "EasyOCR Pipeline" if ocr_active else "Simulated OCR Engine (Torch Missing)"
        
        for img_path in image_paths:
            img_records = process_image_file(img_path, company, pdf_name)
            records.extend(img_records)
            
            # Clean up page image to save space
            try:
                os.remove(img_path)
            except Exception as e:
                logger.error(f"Failed to delete temp image {img_path}: {e}")

        # 3. Save to JSON
        success = self.json_manager.save_pdf_records(company, pdf_name, records)
        return {
            "success": success,
            "record_count": len(records),
            "method": method_str,
            "pdf_name": pdf_name,
            "company": company
        }

    def process_image_ocr(self, image_path, company):
        """
        Handles direct table extraction from uploaded PNG/JPG raw images.
        """
        image_name = os.path.basename(image_path)
        ocr_active = is_ocr_available()
        method_str = "EasyOCR Pipeline" if ocr_active else "Simulated OCR Engine (Torch Missing)"
        
        # Process image directly
        records = process_image_file(image_path, company, image_name)
        
        # Save to JSON
        success = self.json_manager.save_pdf_records(company, image_name, records)
        return {
            "success": success,
            "record_count": len(records),
            "method": method_str,
            "pdf_name": image_name,
            "company": company
        }
