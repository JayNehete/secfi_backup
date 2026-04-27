import os
import re
import json
import requests
from datetime import datetime
from bs4 import BeautifulSoup

# This will be updated to point to S3 later in Phase 2
OUTPUT_DIR = "extraction_results"

def download_html(url, headers):
    """Downloads the raw SEC filing HTML."""
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

def clean_html(html_content):
    """
    RAG-Optimization: Cleans HTML tags and surgically removes raw numerical tables 
    so the embedding model only ingests high-quality narrative text.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove dense data tables to prevent vector garbage
    for table in soup.find_all('table'):
        # Heuristic: If a table has more than 10 numbers in it, it's financial math, not narrative.
        # We delete it because numerical_extractor.py handles the math securely.
        if len(re.findall(r'\d+', table.get_text())) > 10:
            table.decompose()
            
    text = soup.get_text(separator='\n')
    
    # Clean up excessive newlines caused by formatting
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text

def parse_items(text, form_type):
    """
    Core Edgar-Crawler logic: Uses regex boundaries to slice the document into 
    specific, highly valuable narrative JSON sections.
    """
    extracted_data = {}
    
    if form_type == "10-K":
        # Regex looks for the explicit header preceded by newlines to avoid false positives
        patterns = {
            "Item 1: Business": re.compile(r'(?i)\n\s*ITEM\s+1\.\s+BUSINESS'),
            "Item 1A: Risk Factors": re.compile(r'(?i)\n\s*ITEM\s+1A\.\s+RISK FACTORS'),
            "Item 7: MD&A": re.compile(r'(?i)\n\s*ITEM\s+7\.\s+MANAGEMENT.*?ANALYSIS'),
            "Item 7A: Quantitative Risk": re.compile(r'(?i)\n\s*ITEM\s+7A\.\s+QUANTITATIVE'),
            "Item 8: Financial Statements": re.compile(r'(?i)\n\s*ITEM\s+8\.\s+FINANCIAL STATEMENTS')
        }
    elif form_type == "10-Q":
        patterns = {
            "Item 2: MD&A": re.compile(r'(?i)\n\s*ITEM\s+2\.\s+MANAGEMENT.*?ANALYSIS'),
            "Item 3: Quantitative Risk": re.compile(r'(?i)\n\s*ITEM\s+3\.\s+QUANTITATIVE'),
            "Item 1A: Risk Factors": re.compile(r'(?i)\n\s*ITEM\s+1A\.\s+RISK FACTORS')
        }
    else:
        return {"Uncategorized_Text": text[:50000]}
        
    positions = {}
    for item, regex in patterns.items():
        matches = list(regex.finditer(text))
        if matches:
            # SEC documents usually have a Table of Contents at the top.
            # The actual section content is almost always the LAST match in the document.
            actual_match = matches[-1]
            positions[item] = actual_match.start()
            
    # Sort the starting positions chronologically as they appear in the text
    sorted_items = sorted(positions.items(), key=lambda x: x[1])
    
    # Extract the text chunks between the consecutive headers
    for i in range(len(sorted_items)):
        item_name, start_idx = sorted_items[i]
        
        # If it's the last item on our list, grab the next 40,000 characters
        if i == len(sorted_items) - 1:
            end_idx = start_idx + 40000 
        else:
            end_idx = sorted_items[i+1][1]
            
        section_text = text[start_idx:end_idx].strip()
        
        # Only save the section if it actually contains substantial text
        if len(section_text) > 500: 
            extracted_data[item_name] = section_text
            
    return extracted_data

def extract_and_save_narrative(cik, company_name, url, form_type, date):
    """Master controller for the text pipeline."""
    print(f"📥 Downloading Narrative HTML for {company_name} ({form_type})...")
    
    # SEC EDGAR requires a valid User-Agent
    headers = {'User-Agent': 'UniversityResearch_Jay (jay.nehete@example.com)'}
    
    try:
        html_content = download_html(url, headers)
        
        print("🧹 Cleaning HTML (Stripping raw numerical tables)...")
        clean_text = clean_html(html_content)
        
        print("🔍 Partitioning Narrative Items (edgar-crawler logic)...")
        parsed_items = parse_items(clean_text, form_type)
        
        if not parsed_items:
            print("⚠️ Could not locate standard Item headers. Document formatting may be non-standard.")
            # Fallback mechanism so RAG still gets something
            parsed_items = {"Full_Text_Fallback": clean_text[:40000]}
            
        # Structure the highly organized JSON
        final_json = {
            "company_name": company_name,
            "cik": cik,
            "form_type": form_type,
            "latest_period_end_date": date,
            "extraction_timestamp": datetime.now().isoformat(),
            "source_url": url,
            "narrative_sections": parsed_items
        }
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"narrative_{cik}_{company_name.replace('/', '_')}_{timestamp}.json"
        
        # Save it to the RAG processing folder
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(final_json, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Saved clean narrative JSON to {filepath}")
        return filepath
        
    except requests.exceptions.RequestException as e:
        print(f"❌ SEC Download Error: {e}")
        return None
    except Exception as e:
        print(f"❌ Error extracting narrative text: {e}")
        return None