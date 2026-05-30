import os
import json
from utils import get_dir, logger

DEFAULT_COMPANIES = [
    "CEAT",
    "YOKOHAMA",
    "GOODYEAR",
    "MICHELIN",
    "MRF",
    "APOLLO",
    "JK TYRE",
    "BRIDGESTONE"
]

class CompanyManager:
    def __init__(self):
        self.companies_file = os.path.join(get_dir("json_data"), "companies.json")
        self.companies = self._load_companies()

    def _load_companies(self):
        """Loads companies from companies.json, or initializes defaults if not present."""
        if os.path.exists(self.companies_file):
            try:
                with open(self.companies_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        # Ensure all defaults are in the loaded list
                        loaded = set(data)
                        for company in DEFAULT_COMPANIES:
                            loaded.add(company)
                        return sorted(list(loaded))
            except Exception as e:
                logger.error(f"Error loading companies.json: {e}")
        
        # Write default companies if file doesn't exist or is invalid
        self._save_companies(DEFAULT_COMPANIES)
        return sorted(DEFAULT_COMPANIES)

    def _save_companies(self, companies_list):
        """Saves the company list to companies.json."""
        try:
            with open(self.companies_file, "w", encoding="utf-8") as f:
                json.dump(companies_list, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving companies.json: {e}")

    def get_all_companies(self):
        """Returns the sorted list of all active companies."""
        return self.companies

    def add_company(self, company_name):
        """Adds a new company to the list. Returns True if successful, False if already exists or invalid."""
        name_clean = company_name.strip().upper()
        if not name_clean:
            return False
        
        # Streamlit or other places might want title or original casing, let's keep original custom casing
        # but normalize check
        for c in self.companies:
            if c.strip().upper() == name_clean:
                return False
        
        self.companies.append(company_name.strip())
        self.companies = sorted(self.companies)
        self._save_companies(self.companies)
        logger.info(f"Custom company added: {company_name.strip()}")
        return True

    def delete_company(self, company_name):
        """Deletes a company from the list. Standard companies cannot be deleted to preserve system defaults."""
        name_clean = company_name.strip()
        if name_clean in DEFAULT_COMPANIES:
            logger.warning(f"Attempted to delete default company: {name_clean}")
            return False
        
        if name_clean in self.companies:
            self.companies.remove(name_clean)
            self._save_companies(self.companies)
            logger.info(f"Company deleted: {name_clean}")
            return True
        return False
