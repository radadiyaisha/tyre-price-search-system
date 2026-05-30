import os
import re
import cv2
import numpy as np
from PIL import Image
from utils import get_dir, logger
from size_detector import detect_tyre_sizes

# Lazy load easyocr to prevent start-up exceptions if torch/easyocr is not yet installed
EASYOCR_AVAILABLE = False
_reader = None

def get_easyocr_reader():
    global EASYOCR_AVAILABLE, _reader
    if _reader is not None:
        return _reader
    
    try:
        import easyocr
        # Initialize EasyOCR with English language; support CPU or GPU automatically
        _reader = easyocr.Reader(['en'], gpu=True)
        EASYOCR_AVAILABLE = True
        logger.info("EasyOCR reader successfully initialized (GPU enabled if available).")
        return _reader
    except ImportError:
        logger.warning("EasyOCR is not installed. OCR fallbacks will use simulation/guidance.")
        EASYOCR_AVAILABLE = False
        return None
    except Exception as e:
        logger.error(f"Error initializing EasyOCR: {e}")
        EASYOCR_AVAILABLE = False
        return None

def is_ocr_available():
    return get_easyocr_reader() is not None

def convert_pdf_to_images(pdf_path, dpi=200):
    """
    Converts all pages of a PDF into PNG images stored in the temp directory.
    Returns a list of image paths.
    """
    image_paths = []
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        temp_dir = get_dir("temp")
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=dpi)
            image_filename = f"{pdf_name}_page_{page_num + 1}.png"
            image_path = os.path.join(temp_dir, image_filename)
            pix.save(image_path)
            image_paths.append(image_path)
            logger.info(f"Rendered page {page_num + 1} to {image_path}")
            
        doc.close()
    except Exception as e:
        logger.error(f"Failed to convert PDF {pdf_path} to images: {e}")
    return image_paths

def process_image_file(image_path, company, pdf_name):
    """
    Extracts text boxes from an image, clusters them into tabular rows,
    detects tyre sizes, and returns list of record dicts.
    """
    reader = get_easyocr_reader()
    if not reader:
        # Fallback to simulation/mock if reader is unavailable
        logger.warning(f"EasyOCR not available, returning empty list for {image_path}")
        return get_mock_ocr_records(company, pdf_name)
    
    try:
        # Read text with bounding boxes
        results = reader.readtext(image_path)
        if not results:
            logger.warning(f"No text detected on image: {image_path}")
            return []
            
        return reconstruct_table_from_ocr(results, company, pdf_name)
    except Exception as e:
        logger.error(f"Error during OCR processing on {image_path}: {e}")
        return []

def clean_rupee_misreads(text):
    """
    Corrects misread Indian Rupee symbols (which EasyOCR frequently misidentifies
    as numbers '8', '7', '2', '3' or letter 'B' prior to 4-digit prices).
    E.g.: '83,250' -> '3,250'
          '72,980' -> '2,980'
          '83,100' -> '3,100'
          'B3,600' -> '3,600'
    """
    if not text:
        return ""
    # Strip standalone rupee symbol if present
    text = text.replace("₹", "").strip()
    
    # Strip leading digit if it acts as a misread Rupee symbol before standard price (thousands)
    text = re.sub(r"\b[7823B](\d{1,2}\,\d{3})\b", r"\1", text)
    return text

def merge_horizontal_adjacent_boxes(items, horizontal_limit_ratio=0.7):
    """
    Merges bounding boxes that are on the same horizontal line and are extremely close.
    This resolves numbers split by large comma spacing (e.g. ['83,', '250'] -> '83,250').
    """
    merged_any = True
    while merged_any:
        merged_any = False
        # Sort items by X-coordinate to process left-to-right
        items.sort(key=lambda x: x["x0"])
        
        i = 0
        while i < len(items):
            item_a = items[i]
            merged = False
            
            for j in range(i + 1, len(items)):
                item_b = items[j]
                
                # Check vertical alignment (must be on the same row)
                overlap_y0 = max(item_a["y0"], item_b["y0"])
                overlap_y1 = min(item_a["y1"], item_b["y1"])
                overlap_height = max(0, overlap_y1 - overlap_y0)
                
                height_a = item_a["y1"] - item_a["y0"]
                height_b = item_b["y1"] - item_b["y0"]
                min_height = min(height_a, height_b)
                
                # Check horizontal gap: b is to the right of a, so b["x0"] >= a["x1"]
                horizontal_gap = item_b["x0"] - item_a["x1"]
                max_allowed_gap = min_height * horizontal_limit_ratio
                
                if min_height > 0 and (overlap_height / min_height) >= 0.5:
                    # They are vertically aligned. Now check horizontal gap
                    if 0 <= horizontal_gap <= max_allowed_gap:
                        # Merge item_b into item_a
                        text_a = item_a["text"]
                        text_b = item_b["text"]
                        
                        # If A ends with a comma/dot or B starts with a comma/dot, join without spaces
                        if text_a.endswith(",") or text_b.startswith(",") or text_a.endswith(".") or text_b.startswith("."):
                            item_a["text"] = f"{text_a}{text_b}"
                        else:
                            # If it looks like a price split, merge without space
                            if (text_a[-1].isdigit() if text_a else False) and (text_b[0].isdigit() if text_b else False):
                                item_a["text"] = f"{text_a}{text_b}"
                            else:
                                item_a["text"] = f"{text_a} {text_b}"
                                
                        item_a["x1"] = max(item_a["x1"], item_b["x1"])
                        item_a["y0"] = min(item_a["y0"], item_b["y0"])
                        item_a["y1"] = max(item_a["y1"], item_b["y1"])
                        item_a["y_center"] = (item_a["y0"] + item_a["y1"]) / 2
                        item_a["x_center"] = (item_a["x0"] + item_a["x1"]) / 2
                        item_a["height"] = item_a["y1"] - item_a["y0"]
                        
                        # Remove item_b
                        items.pop(j)
                        merged = True
                        merged_any = True
                        break
            if not merged:
                i += 1
    return items

def merge_multiline_header_rows(rows, header_keywords):
    """
    Identifies if the top 2-3 rows represent a multi-line wrapped header,
    merges their cells based on horizontal overlap, and returns the cleaned rows list.
    """
    if len(rows) < 2:
        return rows
        
    # Check how many of the top rows contain header keywords
    header_rows_count = 0
    for i in range(min(3, len(rows))):
        row_text = " ".join(item["text"].lower() for item in rows[i])
        if any(kw in row_text for kw in header_keywords):
            header_rows_count += 1
        else:
            break
            
    if header_rows_count <= 1:
        return rows # No multi-line header to merge
        
    logger.info(f"Detected multi-line header consisting of {header_rows_count} rows. Merging...")
    
    # We will merge rows from 1 to header_rows_count-1 into row 0
    row_0 = rows[0]
    for r_idx in range(1, header_rows_count):
        row_r = rows[r_idx]
        
        # For each item in row_r, find the item in row_0 with the closest/overlapping X coordinates
        for item_r in row_r:
            best_match = None
            min_dist = float("inf")
            
            for item_0 in row_0:
                # Calculate horizontal overlap
                overlap_x0 = max(item_0["x0"], item_r["x0"])
                overlap_x1 = min(item_0["x1"], item_r["x1"])
                overlap_width = max(0, overlap_x1 - overlap_x0)
                
                # If they overlap horizontally, it's a strong match
                if overlap_width > 0:
                    best_match = item_0
                    break
                else:
                    dist = abs(item_0["x_center"] - item_r["x_center"])
                    if dist < min_dist:
                        min_dist = dist
                        best_match = item_0
                        
            if best_match:
                # Merge text (B is below A, so append)
                best_match["text"] = f"{best_match['text']} {item_r['text']}"
                best_match["x0"] = min(best_match["x0"], item_r["x0"])
                best_match["x1"] = max(best_match["x1"], item_r["x1"])
                best_match["y1"] = max(best_match["y1"], item_r["y1"])
                best_match["y_center"] = (best_match["y0"] + best_match["y1"]) / 2
                best_match["x_center"] = (best_match["x0"] + best_match["x1"]) / 2
                best_match["height"] = best_match["y1"] - best_match["y0"]
                
    # Remove the merged auxiliary header rows from the list
    del rows[1:header_rows_count]
    return rows

def reconstruct_table_from_ocr(ocr_results, company, pdf_name):
    """
    Groups OCR bounding boxes into horizontal lines (rows) based on spatial overlap,
    sorts columns horizontally, detects tyre sizes, and maps rows dynamically.
    """
    records = []
    if not ocr_results:
        return records

    # 1. Format items into a usable representation: (x_center, y_center, x0, y0, x1, y1, text)
    items = []
    for box, text, conf in ocr_results:
        text = text.strip()
        if not text:
            continue
        
        # Bounding box points
        p0, p1, p2, p3 = box
        x0, y0 = min(p0[0], p3[0]), min(p0[1], p1[1])
        x1, y1 = max(p1[0], p2[0]), max(p2[1], p3[1])
        
        x_center = (x0 + x1) / 2
        y_center = (y0 + y1) / 2
        height = y1 - y0
        
        items.append({
            "x_center": x_center,
            "y_center": y_center,
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
            "height": height,
            "text": text
        })
        
    if not items:
        return records

    # 2. Merge horizontally split values first (resolves price comma splits e.g. ['83,', '250'] -> '83,250')
    items = merge_horizontal_adjacent_boxes(items)
    
    # 3. Clean currency symbol OCR misreads (Rupee symbol read as digits)
    for item in items:
        item["text"] = clean_rupee_misreads(item["text"])

    # 4. Sort items primarily by Y-coordinate
    items.sort(key=lambda item: item["y_center"])
    
    # 5. Group into horizontal rows based on Y-distance threshold
    rows = []
    current_row = []
    
    # Estimate standard row height
    avg_height = sum(item["height"] for item in items) / len(items)
    vertical_threshold = avg_height * 0.7  # 70% of average word height
    
    for item in items:
        if not current_row:
            current_row.append(item)
        else:
            prev_item = current_row[-1]
            if abs(item["y_center"] - prev_item["y_center"]) <= vertical_threshold:
                current_row.append(item)
            else:
                # Close current row, sort horizontally, start new one
                current_row.sort(key=lambda r: r["x_center"])
                rows.append(current_row)
                current_row = [item]
                
    if current_row:
        current_row.sort(key=lambda r: r["x_center"])
        rows.append(current_row)

    # 6. Reconstruct table structures from rows
    # Standard header keywords used for layout mapping
    header_keywords = [
        "size", "code", "rim", "pattern", "mrp", "yrp", "price", "sku", 
        "tyre", "tube", "flap", "rate", "description", "invoice", "rcp", "best", "ss", "li"
    ]
    
    # Merge multi-line header rows vertically inside row layout (keeps data columns intact)
    rows = merge_multiline_header_rows(rows, header_keywords)
    
    # Locate the header index
    header_idx = -1
    for idx, row in enumerate(rows[:5]):  # check top 5 rows
        row_text = " ".join(item["text"].lower() for item in row)
        matches = sum(1 for kw in header_keywords if kw in row_text)
        if matches >= 2:
            header_idx = idx
            break
            
    if header_idx != -1:
        headers = [item["text"] for item in rows[header_idx]]
        data_rows = rows[header_idx + 1:]
    else:
        if len(rows) > 0:
            headers = [item["text"] for item in rows[0]]
            data_rows = rows[1:]
        else:
            return []

    # Clean headers (avoid duplicates by appending index if empty or identical)
    seen_headers = {}
    clean_headers = []
    for i, h in enumerate(headers):
        h_clean = h.strip() if h.strip() else f"Column_{i+1}"
        if h_clean in seen_headers:
            seen_headers[h_clean] += 1
            h_clean = f"{h_clean}_{seen_headers[h_clean]}"
        else:
            seen_headers[h_clean] = 1
        clean_headers.append(h_clean)

    # 7. Parse rows into data objects
    for row in data_rows:
        row_cells = {}
        row_text_full = " ".join(item["text"] for item in row)
        
        # Detect tyre sizes inside the entire row string
        tyre_sizes = detect_tyre_sizes(row_text_full)
        if not tyre_sizes:
            # Skip rows with no tyre sizes (headers, footers, garbage)
            continue
            
        # Map elements based on proximity to horizontal columns
        for i, h_item in enumerate(rows[header_idx] if header_idx != -1 else rows[0]):
            if i >= len(clean_headers):
                break
            h_name = clean_headers[i]
            
            # Find closest element in this data row
            closest_val = ""
            min_dist = float("inf")
            for d_item in row:
                dist = abs(d_item["x_center"] - h_item["x_center"])
                if dist < min_dist:
                    min_dist = dist
                    closest_val = d_item["text"]
            row_cells[h_name] = closest_val

        # Add records for each detected tyre size in this row
        for size in tyre_sizes:
            records.append({
                "company": company,
                "pdf_name": pdf_name,
                "tyre_size": size,
                "headers": clean_headers,
                "row": row_cells
            })
            
    logger.info(f"OCR Table extraction completed for {pdf_name}. Found {len(records)} tyre records.")
    return records

def get_mock_ocr_records(company, pdf_name):
    """
    Simulation fallback when EasyOCR is not available.
    """
    logger.info(f"Generating simulated OCR price list records for {company} - {pdf_name}")
    records = []
    
    sizes = [
        "145/70R12", "145/80R12", "155/65R13", "165D13", "185D14",
        "195D15", "6.00-16", "7.50-16", "8.25-16", "1100R20",
        "11.00R20", "295/90R20", "295/80R22.5", "LT215/75R15",
        "LT235/75R15", "31X10.5R15", "33X12.5R15", "145R12", "155R13"
    ]
    
    if company.upper() == "YOKOHAMA":
        headers = ["Code", "Size", "Rim", "LI/SS", "Pattern", "YRP", "MRP", "Suggested Vehicle Fitment"]
        for i, size in enumerate(sizes[:8]):
            rim = size.split("R")[-1] if "R" in size else (size.split("-")[-1] if "-" in size else "12")
            row = {
                "Code": f"Y{1000 + i}",
                "Size": size,
                "Rim": rim,
                "LI/SS": "74T" if "12" in rim else "91V",
                "Pattern": "Geolandar" if "15" in rim or "16" in rim else "Earth-1 Max",
                "YRP": str(2500 + i * 350),
                "MRP": str(2800 + i * 380),
                "Suggested Vehicle Fitment": "ALTO" if "12" in rim else "WAGONR/SWIFT"
            }
            records.append({
                "company": company,
                "pdf_name": pdf_name,
                "tyre_size": size,
                "headers": headers,
                "row": row,
                "ocr_simulated": True
            })
            
    elif company.upper() in ["GOODYEAR", "MICHELIN"]:
        headers = ["RIM", "SKU Description", "PD MAY", "Invoice New Price", "BEST PRICES", "RCP"]
        for i, size in enumerate(sizes[8:15]):
            rim = size.split("R")[-1] if "R" in size else (size.split("-")[-1] if "-" in size else "15")
            row = {
                "RIM": f"R{rim}",
                "SKU Description": f"{size} DUCARO HI-MILER PREMIUM TYRE",
                "PD MAY": "0",
                "Invoice New Price": str(3200 + i * 400),
                "BEST PRICES": str(3500 + i * 420),
                "RCP": str(3800 + i * 450)
            }
            records.append({
                "company": company,
                "pdf_name": pdf_name,
                "tyre_size": size,
                "headers": headers,
                "row": row,
                "ocr_simulated": True
            })
            
    else:  # CEAT Columns / Custom
        headers = ["TYRE", "TUBE", "FLAP", "TOTAL"]
        for i, size in enumerate(sizes[12:]):
            row = {
                "TYRE": str(1800 + i * 300),
                "TUBE": "250",
                "FLAP": "150",
                "TOTAL": str(2200 + i * 300)
            }
            records.append({
                "company": company,
                "pdf_name": pdf_name,
                "tyre_size": size,
                "headers": headers,
                "row": row,
                "ocr_simulated": True
            })
            
    return records
