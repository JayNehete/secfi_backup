import requests
import json
from datetime import datetime, timedelta
from sec_api import ExtractorApi
from url_finder import get_latest_filing_url

# Load configuration
try:
    with open('config.json', 'r') as f:
        CONFIG = json.load(f)
    USER_AGENT = CONFIG.get("user_agent", "Example Inc. (example@example.com)")
    SEC_API_IO_KEY = CONFIG.get("sec_api_io_key", "91fd6910ddf38d2b9941841e6141dc588223d95091f78be2d2565509a32ada4b")
except FileNotFoundError:
    USER_AGENT = "Example Inc. (example@example.com)"
    SEC_API_IO_KEY = "91fd6910ddf38d2b9941841e6141dc588223d95091f78be2d2565509a32ada4b"

HEADERS = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}

def get_cik_by_ticker(ticker):
    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        tickers_data = response.json()
        ticker_upper = ticker.upper()
        for entry in tickers_data.values():
            if entry['ticker'] == ticker_upper:
                return str(entry['cik_str']).zfill(10)
        return None
    except Exception as e:
        print(f"Error fetching CIK for {ticker}: {e}")
        return None

def get_recent_filers(lookback_days=5):
    target_forms = ['10-Q', '10-K', '8-K']
    recent_filers = {}
    current_date = datetime.now()
    
    for i in range(lookback_days):
        date_to_check = current_date - timedelta(days=i)
        if date_to_check.weekday() >= 5: continue
            
        year = date_to_check.year
        quarter = (date_to_check.month - 1) // 3 + 1
        date_str_url = date_to_check.strftime('%Y%m%d')
        date_str_display = date_to_check.strftime('%Y-%m-%d')
        index_url = f"https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/master.{date_str_url}.idx"
        
        try:
            response = requests.get(index_url, headers=HEADERS)
            if response.status_code == 404: continue
            response.raise_for_status()
            
            for line in response.text.splitlines():
                if not line or '|' not in line: continue
                parts = line.split('|')
                if len(parts) != 5: continue
                cik, name, form_type, date_filed, filename = parts
                cik = str(cik).strip().zfill(10)
                form_type = form_type.strip()
                if any(form_type.startswith(t) for t in target_forms):
                    if cik not in recent_filers:
                        recent_filers[cik] = date_str_display
            
            if recent_filers:
                return recent_filers
        except Exception as e:
            continue
    return recent_filers

def get_company_facts(cik):
    """
    Fetches company facts data from SEC API for numerical extraction.
    """
    cik = str(cik).zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching company facts for CIK {cik}: {e}")
        return None

def get_risk_factors_via_api(cik):
    """
    Uses sec-api.io ExtractorApi to get narrative text (Risk Factors).
    Automatically switches section IDs based on 10-K vs 10-Q.
    """
    extractorApi = ExtractorApi(SEC_API_IO_KEY)

    url, form_type = get_latest_filing_url(cik)

    if not url:
        return None, None

    section_id = "1A"
    if form_type and "10-Q" in form_type:
        section_id = "part2item1a"

    print(f"Extracting section '{section_id}' from {form_type}...")

    try:
        text = extractorApi.get_section(url, section_id, "text")

        company_name = get_company_name(cik)

        metadata = {
            "cik": cik,
            "company_name": company_name,
            "form": form_type,
            "url": url,
            "section": "Risk Factors"
        }

        return text, metadata
    except Exception as e:
        print(f"Error extracting text snippet: {e}")
        return None, None

def get_company_name(cik):
    """
    Gets company name from company facts API.
    """
    cik = str(cik).zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            return data.get('entityName', 'Unknown')
    except Exception:
        pass
    return 'Unknown'