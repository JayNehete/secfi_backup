import json
import os
import time
from datetime import datetime
from sec_api_f import get_recent_filers
from extractor import extract_financial_data

OUTPUT_DIR = 'extraction_results'

def ensure_output_dir():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

def save_numerical_data(data):
    if not data:
        return None

    company_name = data.get('company_name', 'Unknown').replace('/', '_').replace('\\', '_')
    cik = data.get('cik', 'unknown')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    filename = f"{OUTPUT_DIR}/numerical_{cik}_{company_name}_{timestamp}.json"

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filename
    except Exception as e:
        print(f"Error saving file: {e}")
        return None

def run_numerical_extraction():
    print("Starting SEC Numerical Data Extraction...")
    print("=" * 60)

    ensure_output_dir()

    recent_filers = get_recent_filers()

    if not recent_filers:
        print("No recent filers found. Exiting.")
        return None

    recent_ciks = list(recent_filers.keys())
    print(f"Found {len(recent_ciks)} recent filers. Processing...")

    all_results = []
    saved_files = []

    for i, cik in enumerate(recent_ciks):
        data = extract_financial_data(cik)

        if data:
            company_name = data.get('company_name', 'Unknown')
            print(f"[{i+1}/{len(recent_ciks)}] SUCCESS: {company_name}")

            saved_file = save_numerical_data(data)
            if saved_file:
                saved_files.append(saved_file)
                print(f"  Saved: {saved_file}")

            all_results.append(data)
            revenue_yoy = data.get('income_statement', {}).get('total_revenue', {}).get('yoy_percent_change')
            if revenue_yoy is not None:
                print(f"  Revenue YoY: {revenue_yoy * 100:.2f}%")

            if i == 0:
                print("\n--- Sample Output ---")
                print(json.dumps(data, indent=2))
                print("---------------------\n")

        time.sleep(0.2)

    print(f"\nExtraction complete. Processed {len(all_results)} companies.")
    print(f"Saved {len(saved_files)} files to {OUTPUT_DIR}/")

    return {
        'results': all_results,
        'saved_files': saved_files
    }

if __name__ == "__main__":
    results = run_numerical_extraction()
