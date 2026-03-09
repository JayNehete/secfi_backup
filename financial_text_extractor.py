import os
import requests
import time
from datetime import datetime
from bs4 import BeautifulSoup
import re
from sec_api_f import get_recent_filers
from url_finder import get_latest_filing_url

OUTPUT_DIR = 'extraction_results'

def load_config():
    import json
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"user_agent": "Test (test@test.com)"}

def ensure_output_dir():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

def get_company_name(cik):
    cik = str(cik).zfill(10)
    config = load_config()
    user_agent = config.get("user_agent", "Test (test@test.com)")

    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    headers = {"User-Agent": user_agent}

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get('entityName', 'Unknown')
    except Exception:
        pass
    return 'Unknown'

def download_filing_html(url):
    config = load_config()
    user_agent = config.get("user_agent", "Test (test@test.com)")

    headers = {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate"
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        else:
            print(f"  Error downloading filing: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"  Error downloading filing: {e}")
        return None

def extract_text_between_headers(html_text, start_header, end_header):
    """
    Extracts text between two headers in HTML filing.
    Looks for header text and extracts everything until next major header.
    """
    # Find start header
    start_match = re.search(
        start_header,
        html_text,
        re.DOTALL | re.IGNORECASE
    )

    if not start_match:
        return None

    # Find end header (or next major section)
    end_match = re.search(
        end_header,
        html_text[start_match.end():],
        re.DOTALL | re.IGNORECASE
    )

    if end_match:
        section_end = start_match.end() + end_match.start() + end_match.end()
        section_html = html_text[start_match.start():section_end]
    else:
        # No end found, take up to next ITEM or end of document
        next_item = re.search(
            r'ITEM\s+[0-9A-Z]+\.?\s+[A-Z]',
            html_text[start_match.end():],
            re.IGNORECASE
        )

        if next_item:
            section_html = html_text[start_match.start():start_match.end() + next_item.start()]
        else:
            # Take last 50000 chars if no clear end
            section_html = html_text[start_match.start():start_match.end() + 50000]

    return section_html

def extract_financial_text_from_html(cik, url, form_type):
    """
    Extracts financial text from filing HTML.

    For 10-K:
      - Item 7: Management's Discussion and Analysis (MD&A)
      - Item 8: Financial Statements

    For 10-Q:
      - Part II, Item 1: Financial Statements
      - Part II, Item 2: MD&A
    """
    print(f"  Downloading filing HTML...")

    html_text = download_filing_html(url)

    if not html_text:
        return None

    extracted_sections = {}

    if form_type == '10-K':
        # Extract MD&A
        print(f"  Extracting MD&A...")
        md_section = extract_text_between_headers(
            html_text,
            r'ITEM\s+7\.?\s+.*MANAGEMENT.*DISCUSSION.*ANALYSIS',
            r'ITEM\s+8'
        )

        if md_section:
            soup = BeautifulSoup(md_section, 'html.parser')
            for table in soup.find_all('table'):
                table.decompose()
            text = soup.get_text(separator='\n', strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text).strip()

            if len(text) > 500:
                extracted_sections['md_and_a'] = {
                    'text': text,
                    'description': "Management's Discussion and Analysis",
                    'length': len(text)
                }
                print(f"    ✓ MD&A: {len(text)} characters")

        # Extract Financial Statements
        print(f"  Extracting Financial Statements...")
        fs_section = extract_text_between_headers(
            html_text,
            r'ITEM\s+8\.?\s+.*FINANCIAL\s+STATEMENTS',
            r'ITEM\s+9|ITEM\s+7\(A\)|QUANTITATIVE|DISCLOSURE'
        )

        if fs_section:
            soup = BeautifulSoup(fs_section, 'html.parser')
            for table in soup.find_all('table'):
                table.decompose()
            text = soup.get_text(separator='\n', strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text).strip()

            if len(text) > 500:
                extracted_sections['financial_statements'] = {
                    'text': text,
                    'description': "Financial Statements and Supplementary Data",
                    'length': len(text)
                }
                print(f"    ✓ Financial Statements: {len(text)} characters")

    else:  # 10-Q
        # Extract Financial Statements
        print(f"  Extracting Financial Statements...")
        fs_section = extract_text_between_headers(
            html_text,
            r'PART\s+II.*ITEM\s+1.*FINANCIAL\s+STATEMENTS',
            r'PART\s+II.*ITEM\s+2|MANAGEMENT.*DISCUSSION'
        )

        if fs_section:
            soup = BeautifulSoup(fs_section, 'html.parser')
            for table in soup.find_all('table'):
                table.decompose()
            text = soup.get_text(separator='\n', strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text).strip()

            if len(text) > 500:
                extracted_sections['financial_statements'] = {
                    'text': text,
                    'description': "Financial Statements",
                    'length': len(text)
                }
                print(f"    ✓ Financial Statements: {len(text)} characters")

        # Extract MD&A
        print(f"  Extracting MD&A...")
        md_section = extract_text_between_headers(
            html_text,
            r'PART\s+II.*ITEM\s+2.*MANAGEMENT.*DISCUSSION.*ANALYSIS',
            r'PART\s+II.*ITEM\s+3|PART\s+III|PART\s+IV|QUANTITATIVE|DISCLOSURE'
        )

        if md_section:
            soup = BeautifulSoup(md_section, 'html.parser')
            for table in soup.find_all('table'):
                table.decompose()
            text = soup.get_text(separator='\n', strip=True)
            text = re.sub(r'\n{3,}', '\n\n', text).strip()

            if len(text) > 500:
                extracted_sections['md_and_a'] = {
                    'text': text,
                    'description': "Management's Discussion and Analysis",
                    'length': len(text)
                }
                print(f"    ✓ MD&A: {len(text)} characters")

    if not extracted_sections:
        print(f"  No sections extracted from filing")
        return None

    company_name = get_company_name(cik)

    result = {
        'cik': cik,
        'company_name': company_name,
        'form_type': form_type,
        'filing_url': url,
        'extraction_date': datetime.now().isoformat(),
        'extraction_method': 'SEC HTML Parsing (Free)',
        'financial_sections': extracted_sections
    }

    return result

def save_financial_text_data(data):
    if not data:
        return None

    company_name = data.get('company_name', 'Unknown').replace('/', '_').replace('\\', '_').replace(' ', '_')
    cik = data.get('cik', 'unknown')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    filename = f"{OUTPUT_DIR}/financial_text_{cik}_{company_name}_{timestamp}.txt"

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("FINANCIAL TEXT EXTRACTION - SEC HTML PARSING\n")
            f.write("(No API quota limits - uses free SEC.gov downloads)\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"Company: {data.get('company_name')}\n")
            f.write(f"CIK: {data.get('cik')}\n")
            f.write(f"Form Type: {data.get('form_type')}\n")
            f.write(f"Filing URL: {data.get('filing_url', 'N/A')}\n")
            f.write(f"Extraction Date: {data.get('extraction_date')}\n")
            f.write(f"Method: {data.get('extraction_method')}\n")
            f.write("\n" + "=" * 80 + "\n\n")

            for section_key, section_data in data.get('financial_sections', {}).items():
                section_name = section_data.get('description', section_key.replace('_', ' ').title())
                f.write(f"SECTION: {section_name}\n")
                f.write(f"Length: {section_data.get('length', 0)} characters\n")
                f.write("-" * 80 + "\n\n")
                f.write(section_data['text'])
                f.write("\n\n" + "=" * 80 + "\n\n")

        return filename
    except Exception as e:
        print(f"Error saving file: {e}")
        return None

def run_financial_text_extraction():
    print("Starting SEC Financial Text Extraction (FREE - No API Limits)")
    print("=" * 80)
    print("Extracting meaningful text related to:")
    print("  - Statement of Operations (MD&A analysis)")
    print("  - Balance Sheet discussions")
    print("  - Cash Flow discussions")
    print("\nMethod: Downloads filing HTML directly from SEC.gov and parses")
    print("        Completely free - no API quotas!")
    print("=" * 80)

    ensure_output_dir()

    recent_filers = get_recent_filers()

    if not recent_filers:
        print("No recent filers found. Exiting.")
        return None

    recent_ciks = list(recent_filers.keys())
    print(f"\nFound {len(recent_ciks)} filers. Processing first 3...")

    all_results = []
    saved_files = []
    limit = 3

    for i, cik in enumerate(recent_ciks[:limit]):
        print(f"\n[{i+1}/{limit}] Processing CIK: {cik}")

        url, form_type = get_latest_filing_url(cik)

        if not url:
            print(f"  No filing URL found")
            continue

        print(f"  Found {form_type}: {url}")

        data = extract_financial_text_from_html(cik, url, form_type)

        if data:
            company_name = data.get('company_name', 'Unknown')

            print(f"  Company: {company_name}")

            sections_count = len(data.get('financial_sections', {}))
            print(f"  Sections extracted: {sections_count}")

            saved_file = save_financial_text_data(data)
            if saved_file:
                saved_files.append(saved_file)
                print(f"  Saved: {saved_file}")

            all_results.append(data)

        time.sleep(0.2)

    print(f"\n" + "=" * 80)
    print(f"Extraction complete. Processed {len(all_results)} companies.")
    print(f"Saved {len(saved_files)} files to {OUTPUT_DIR}/")
    print("No API quota used - all downloads from SEC.gov!")
    print("=" * 80)

    return {
        'results': all_results,
        'saved_files': saved_files
    }

if __name__ == "__main__":
    results = run_financial_text_extraction()
