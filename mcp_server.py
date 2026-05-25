import os
import json
import glob
import faiss
import pickle
import numpy as np
import sys  # <-- 1. Import sys
from sentence_transformers import SentenceTransformer
from mcp.server.fastmcp import FastMCP

# --- Configuration ---
OUTPUT_DIR = "extraction_results"
INDEX_PATH = "faiss_index"
CHUNKS_PATH = "chunks.pkl"

sys.stderr.write("🔄 Initializing Triple Engine MCP Server...\n") # <-- 2. Change prints to stderr
mcp = FastMCP("SEC_Financial_Research_Server")

# --- Load RAG Resources into Memory ---
try:
    sys.stderr.write("Loading embedding model...\n")
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    sys.stderr.write("Loading FAISS index...\n")
    index = faiss.read_index(INDEX_PATH)
    with open(CHUNKS_PATH, "rb") as f:
        chunks = pickle.load(f)
    sys.stderr.write("✅ RAG Engine Loaded!\n")
except Exception as e:
    sys.stderr.write(f"⚠️ Warning: RAG Engine failed to load. Error: {e}\n")
    embedder, index, chunks = None, None, None

# ==========================================
# SKILL 1: ENGINE 1 (DETERMINISTIC MATH)
# ==========================================
@mcp.tool()
def get_financial_math(cik: str, metric: str) -> str:
    """
    Skill 1: Deterministic Financial Math.
    Use this tool to get 100% accurate SEC numbers and Year-over-Year (YoY) changes.
    
    Args:
        cik: The 10-digit Central Index Key of the company.
        metric: The specific financial metric (e.g., 'total_revenue', 'gross_profit', 'net_income', 'operating_cash_flow', 'total_assets').
    """
    pattern = os.path.join(OUTPUT_DIR, f"numerical_{cik}_*.json")
    files = glob.glob(pattern)
    if not files:
        return f"Error: No numerical data found for CIK {cik}."
    
    # Grab the most recent extraction for this company
    latest_file = max(files, key=os.path.getctime)
    
    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    metric_clean = metric.lower().replace(' ', '_')
    
    # Search through the financial statements for the exact metric
    for section in ['income_statement', 'balance_sheet', 'cash_flow']:
        section_data = data.get(section, {})
        if metric_clean in section_data:
            vals = section_data[metric_clean]
            curr_val = vals.get('current', {}).get('val', 'N/A')
            prior_val = vals.get('prior', {}).get('val', 'N/A')
            yoy = vals.get('yoy_percent_change', 'N/A')
            
            # Format nicely for the AI to read
            if isinstance(yoy, (int, float)):
                direction = "increase" if yoy > 0 else "decrease"
                yoy_str = f"{abs(yoy) * 100:.2f}% {direction}"
            else:
                yoy_str = str(yoy)
                
            # If the value is a number, format it with commas
            curr_str = f"${curr_val:,.2f}" if isinstance(curr_val, (int, float)) else str(curr_val)
            prior_str = f"${prior_val:,.2f}" if isinstance(prior_val, (int, float)) else str(prior_val)
                
            return f"Metric: {metric.replace('_', ' ').title()}\nCurrent Value: {curr_str}\nPrior Value: {prior_str}\nYoY Change: {yoy_str}"
            
    return f"Error: Metric '{metric}' not found in the filings for CIK {cik}."

# ==========================================
# SKILL 2: ENGINE 3 (EDGAR-CRAWLER TEXT)
# ==========================================
@mcp.tool()
def get_specific_filing_item(cik: str, item_name: str) -> str:
    """
    Skill 2: Edgar-Crawler Item Retrieval.
    Use this tool when you need to read an entire, specific section of a filing verbatim.
    
    Args:
        cik: The 10-digit Central Index Key.
        item_name: The item name (e.g., 'Item 1A: Risk Factors', 'Item 7: MD&A', 'Item 1: Business').
    """
    pattern = os.path.join(OUTPUT_DIR, f"narrative_{cik}_*.json")
    files = glob.glob(pattern)
    if not files:
        return f"Error: No narrative JSON data found for CIK {cik}."
        
    latest_file = max(files, key=os.path.getctime)
    
    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    sections = data.get('narrative_sections', {})
    
    # Fuzzy match the item name so the AI doesn't fail if it types "item 1a" instead of "Item 1A"
    for key, text in sections.items():
        if item_name.lower().replace(' ', '') in key.lower().replace(' ', ''):
            return f"--- START OF {key.upper()} ---\n\n{text}\n\n--- END OF {key.upper()} ---"
            
    return f"Error: Section '{item_name}' was not found. Available sections: {list(sections.keys())}"

# ==========================================
# SKILL 3: ENGINE 2 (SEMANTIC RAG)
# ==========================================
@mcp.tool()
def query_narrative_rag(query: str, cik: str | None = None) -> str:
    """
    Skill 3: Semantic Narrative RAG.
    Use this tool to search the vector database for qualitative context, strategy, or risks.
    
    Args:
        query: The specific question to search for (e.g., "What are the supply chain risks?").
        cik: (Optional) The 10-digit CIK to filter the results to a specific company.
    """
    if index is None or embedder is None:
        return "Error: RAG index is offline."
        
    # Safety check if the AI passes null
    if cik is None:
        cik = ""
        
    # If the AI provides a CIK, we fetch more chunks initially to filter them down
    k_fetch = 20 if cik else 5
    
    query_embedding = embedder.encode([query])
    distances, indices = index.search(np.array(query_embedding), k_fetch)
    
    retrieved_chunks = [chunks[i] for i in indices[0]]
    
    # Post-retrieval filtering (Because we used Dense Contextual Ingestion!)
    if cik:
        filtered_chunks = [c for c in retrieved_chunks if str(cik) in c]
        retrieved_chunks = filtered_chunks[:4]
        if not retrieved_chunks:
            return f"No relevant narrative chunks found specifically for CIK {cik} matching that query."
    else:
        retrieved_chunks = retrieved_chunks[:5]
        
    combined_context = "\n\n---\n\n".join(retrieved_chunks)
    return f"Retrieved SEC Context for your synthesis:\n\n{combined_context}"

if __name__ == "__main__":
    # Runs the server securely over stdio
    mcp.run()