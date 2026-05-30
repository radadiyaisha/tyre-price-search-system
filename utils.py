import os
import logging
from datetime import datetime

# Define workspace directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIRS = {
    "uploads": os.path.join(BASE_DIR, "uploads"),
    "json_data": os.path.join(BASE_DIR, "json_data"),
    "processed_data": os.path.join(BASE_DIR, "processed_data"),
    "search_index": os.path.join(BASE_DIR, "search_index"),
    "logs": os.path.join(BASE_DIR, "logs"),
    "temp": os.path.join(BASE_DIR, "temp")
}

def init_directories():
    """Create all required directories if they do not exist."""
    for dir_name, dir_path in DIRS.items():
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

# Initialize directories on import
init_directories()

# Setup Logging
log_file = os.path.join(DIRS["logs"], "app.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("TyreIntelligence")

def get_dir(name):
    """Retrieve the absolute path of a predefined directory."""
    return DIRS.get(name)

def clean_temp_dir():
    """Clear all files in the temp directory."""
    temp_path = DIRS["temp"]
    for filename in os.listdir(temp_path):
        file_path = os.path.join(temp_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
        except Exception as e:
            logger.error(f"Failed to delete temp file {file_path}: {e}")
