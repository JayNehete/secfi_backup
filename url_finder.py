import requests
import json

HEADERS = {
    "User-Agent": "MyDataApp/1.0 (test@example.com)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov"
}

def get_latest_filing_url(cik):
    """
    Finds the URL and Form Type of the most recent 10-Q or 10-K filing.
    
    Args:
        cik (str): The 10-digit CIK.
    
    Returns:
        tuple: (url, form_type) e.g. ("https://...", "10-K"), or (None, None) if not found.
    """
    cik = str(cik).zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        recent_filings = data.get('filings', {}).get('recent', {})
        forms = recent_filings.get('form', [])
        accession_numbers = recent_filings.get('accessionNumber', [])
        primary_documents = recent_filings.get('primaryDocument', [])
        filing_dates = recent_filings.get('filingDate', [])
        
        for i, form in enumerate(forms):
            # Check for 10-Q or 10-K (and 10-K/A, 10-Q/A amendments)
            if form.startswith('10-Q') or form.startswith('10-K'):
                acc_num = accession_numbers[i]
                primary_doc = primary_documents[i]
                acc_num_no_dashes = acc_num.replace('-', '')
                
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num_no_dashes}/{primary_doc}"
                
                print(f"Found latest {form} for CIK {cik}: {filing_url}")
                return filing_url, form
                
        print(f"No 10-Q or 10-K found in recent history for CIK {cik}")
        return None, None

    except Exception as e:
        print(f"Error fetching filing history for CIK {cik}: {e}")
        return None, None