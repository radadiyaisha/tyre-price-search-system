import re

# Comprehensive list of tyre size regexes (compiled for performance)
TYRE_PATTERNS = [
    # Flotation size: 31X10.5R15, 33X12.5R15
    re.compile(r"\b(\d{2})\s*[xX]\s*(\d{2}\.\d+)\s*[rR]\s*(\d{2})\b"),
    
    # Radial Passenger / Truck (standard & bias ratio): 145/70R12, 295/95D20, 295/80R22.5, LT215/75R15
    re.compile(r"\b(?:LT)?(\d{3})\s*/\s*(\d{2})\s*[rRdD\-]\s*(\d{2}(?:\.\d+)?)\b", re.IGNORECASE),
    
    # Bias ply / standard truck size with decimal: 11.00R20, 6.00-16, 7.50-16, 8.25-16, 11.00-20
    re.compile(r"\b(\d{1,2}\.\d{2})\s*[\-rRdD]\s*(\d{2})\b", re.IGNORECASE),
    
    # Large bias / truck tyre sizes (no decimal): 1100R20, 1000R20
    re.compile(r"\b(\d{4})\s*[rR]\s*(\d{2})\b", re.IGNORECASE),
    
    # Width D Rim (bias standard): 165D13, 185D14, 195D15
    re.compile(r"\b(\d{3})\s*[dD]\s*(\d{2})\b", re.IGNORECASE),
    
    # Radial short: 145R12, 155R13, 145R12C
    re.compile(r"\b(\d{3})\s*[rR]\s*(\d{2})\b", re.IGNORECASE)
]

def clean_extracted_size(pattern_type, match):
    """
    Standardizes matched groups back to a clean string format.
    E.g. (145, 70, 12) -> 145/70R12
    """
    if pattern_type == 0:  # Flotation (31X10.5R15)
        return f"{match.group(1)}X{match.group(2)}R{match.group(3)}".upper()
    elif pattern_type == 1:  # Radial Passenger (145/70R12, 295/95D20)
        # Check if the original matched prefix has 'LT'
        prefix = "LT" if match.group(0).upper().startswith("LT") else ""
        # Preserve original separator (D, -, or R)
        orig = match.group(0).upper()
        sep = "-" if "-" in orig else ("D" if "D" in orig else "R")
        return f"{prefix}{match.group(1)}/{match.group(2)}{sep}{match.group(3)}".upper()
    elif pattern_type == 2:  # Decimal truck (6.00-16 or 11.00R20)
        # Preserve original separator (dash or R/D)
        sep = "-" if "-" in match.group(0) else ("D" if "D" in match.group(0).upper() else "R")
        return f"{match.group(1)}{sep}{match.group(2)}".upper()
    elif pattern_type == 3:  # Large Truck 1100R20
        return f"{match.group(1)}R{match.group(2)}".upper()
    elif pattern_type == 4:  # Bias D (165D13)
        return f"{match.group(1)}D{match.group(2)}".upper()
    elif pattern_type == 5:  # Radial Short (145R12)
        return f"{match.group(1)}R{match.group(2)}".upper()
    return match.group(0).strip().upper()

def detect_tyre_sizes(text):
    """
    Scans a block of text and returns a list of unique detected tyre sizes in standard format.
    """
    if not text or not isinstance(text, str):
        return []
    
    detected = []
    # Test each pattern in order of specificity
    for idx, pattern in enumerate(TYRE_PATTERNS):
        for match in pattern.finditer(text):
            standardized = clean_extracted_size(idx, match)
            if standardized not in detected:
                detected.append(standardized)
                
    return detected

def canonicalize(size_str):
    """
    Generates a canonical form for exact tyre matches by removing spaces, slashes,
    dashes, periods, and optional 'LT' prefixes.
    E.g.: 'LT215/75R15' -> '21575r15'
          '11.00R20' -> '1100r20'
          '6.00-16' -> '60016'
    """
    if not size_str:
        return ""
    
    # Lowercase
    c = size_str.lower().strip()
    # Strip LT prefix
    if c.startswith("lt"):
        c = c[2:]
    
    # Strip flotation separator 'x'
    c = c.replace("x", "")
    
    # Strip symbols
    c = re.sub(r"[^a-z0-9]", "", c)
    return c
