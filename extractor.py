import json
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from sec_api_f import get_company_facts

CONFIG_PATH = 'config.json'

def load_config():
    """Load the entity configuration file."""
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file '{CONFIG_PATH}' not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not parse '{CONFIG_PATH}'. Check for JSON errors.")
        return None

def calculate_yoy(current_val, prior_val):
    """Calculate Year-over-Year percentage change (returns ratio, e.g., 0.10 for 10%)."""
    if prior_val is None or prior_val == 0:
        return None
    try:
        current_val = float(current_val)
        prior_val = float(prior_val)
        yoy_change = ((current_val - prior_val) / abs(prior_val))
        return round(yoy_change, 4)
    except (ValueError, TypeError):
        return None

def get_latest_period_end_date(facts_data, accepted_forms):
    """
    Determines the absolute latest reporting period end date from all facts
    to set a strict cutoff for relevant data.
    """
    latest_date = None
    if 'facts' not in facts_data:
        return None
        
    us_gaap = facts_data['facts'].get('us-gaap', {})
    
    # Iterate through all facts for all tags
    for tag_data in us_gaap.values():
        for unit_data in tag_data.get('units', {}).values():
            for fact in unit_data:
                if fact.get('form') in accepted_forms and fact.get('end'):
                    try:
                        current_date = datetime.strptime(fact['end'], '%Y-%m-%d').date()
                        if latest_date is None or current_date > latest_date:
                            latest_date = current_date
                    except ValueError:
                        continue
                        
    return latest_date


def get_comparable_facts(facts_data, tag_list, acceptable_forms, latest_period_end_date):
    """
    Extracts the latest fact and the comparable prior year fact for a given tag,
    strictly filtering for data relevant to the *most recent reporting period*.
    
    Args:
        facts_data (dict): The complete company facts data from the SEC API.
        tag_list (list): A list of US-GAAP tags to try.
        acceptable_forms (list): List of accepted filing forms (e.g., ['10-Q', '10-K']).
        latest_period_end_date (datetime.date): The most recent reporting period found in ALL facts.
    
    Returns:
        dict: A dictionary containing current fact, prior fact, and YoY change, or None.
    """
    if 'facts' not in facts_data or 'us-gaap' not in facts_data['facts']:
        return None
        
    us_gaap_data = facts_data['facts']['us-gaap']
    
    # 1. Find the facts list for the first available tag in the priority list
    facts_for_tag = None
    for tag in tag_list:
        if tag in us_gaap_data and 'USD' in us_gaap_data[tag].get('units', {}):
            facts_for_tag = us_gaap_data[tag]['units']['USD']
            break
    
    if not facts_for_tag:
        return None
        
    # 2. Define the target comparison periods
    try:
        # Define the most recent period we are targeting (e.g., if latest is 2025-09-30, we target Q3/2025)
        target_period_end = latest_period_end_date.strftime('%Y-%m-%d')
        # Define the prior year target period (e.g., 2024-09-30)
        prior_year_target_period_end = (latest_period_end_date - relativedelta(years=1)).strftime('%Y-%m-%d')
        
    except Exception:
        return None

    current_fact = None
    prior_year_fact = None

    # Search for the CURRENT fact corresponding to the absolute latest period end date
    for fact in facts_for_tag:
        if fact.get('form') in acceptable_forms and fact.get('end') == target_period_end:
            # Prefer '10-Q' or '10-K' filing type if available, but take the first match
            if current_fact is None or fact.get('form') == '10-Q' or fact.get('form') == '10-K':
                current_fact = fact
    
    if not current_fact:
        return None

    # Search for the PRIOR YEAR comparable fact
    for fact in facts_for_tag:
        # Look for the same reporting form and the exact prior year end date
        if fact.get('form') == current_fact['form'] and fact.get('end') == prior_year_target_period_end:
            prior_year_fact = fact
            break
    
    # 3. Calculate YoY and format the result
    prior_val = prior_year_fact['val'] if prior_year_fact else None
    yoy_change = calculate_yoy(current_fact['val'], prior_val)
    
    # Remove 'frame' field as it's often confusing and internal XBRL format
    current_fact.pop('frame', None)
    if prior_year_fact:
        prior_year_fact.pop('frame', None)
    
    return {
        "current": current_fact,
        "prior": prior_year_fact,
        "yoy_percent_change": yoy_change
    }

def extract_financial_data(cik):
    """
    Main function to extract financial statements based on config.json, 
    with a strict check for the current fiscal year.
    
    Args:
        cik (str): 10-digit CIK number
    
    Returns:
        dict: Complete financial data with YoY calculations, or None if skipped.
    """
    config = load_config()
    if not config:
        return None
        
    facts_data = get_company_facts(cik)
    if not facts_data:
        return None
    
    acceptable_forms = config.get("acceptable_forms", ["10-Q", "10-K"])
    
    # CRITICAL CHECK: Determine the latest period end date across ALL facts.
    latest_period_end = get_latest_period_end_date(facts_data, acceptable_forms)
    
    if not latest_period_end:
        print(f"[SKIPPED: {facts_data.get('entityName', 'Unknown')}] Reason: Could not determine any latest reporting period.")
        return None
        

    
    # 1. Initialize result structure with metadata
    result = {
        'company_name': facts_data.get('entityName', ''),
        'cik': cik,
        'extraction_timestamp': datetime.now().isoformat(),
        'latest_period_end_date': latest_period_end.strftime('%Y-%m-%d'),
        'income_statement': {},
        'balance_sheet': {},
        'cash_flow': {}
    }
    
    # 2. Process Income Statement tags
    for key, tag_list in config.get('financial_tags', {}).get('income_statement', {}).items():
        fact_data = get_comparable_facts(facts_data, tag_list, acceptable_forms, latest_period_end)
        if fact_data:
            result['income_statement'][key] = fact_data
    
    # 3. Process Balance Sheet tags
    for key, tag_list in config.get('financial_tags', {}).get('balance_sheet', {}).items():
        fact_data = get_comparable_facts(facts_data, tag_list, acceptable_forms, latest_period_end)
        if fact_data:
            result['balance_sheet'][key] = fact_data

    for key, tag_list in config.get('financial_tags', {}).get('cash_flow', {}).items():
        fact_data = get_comparable_facts(facts_data, tag_list, acceptable_forms, latest_period_end)
        if fact_data:
            result['cash_flow'][key] = fact_data
            
    # Add filing metadata using the first successfully extracted BS item (Total Assets is a good proxy)
    metadata_source = result['balance_sheet'].get('total_assets', {}).get('current', {})
    if metadata_source:
        result['filed_date'] = metadata_source.get('filed')
        result['form_type'] = metadata_source.get('form')
    
    # Ensure there's useful data before returning
    if not result['income_statement'] and not result['balance_sheet']:
        print(f"[SKIPPED: {facts_data.get('entityName', 'Unknown')}] Reason: No high-value financial data found for latest period.")
        return None
            
    return result