import os
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
import pickle

# Changed to match your extractor output directory
DATA_PATH = "extraction_results" 
INDEX_PATH = "faiss_index"
CHUNKS_PATH = "chunks.pkl"

def format_financial_json_to_text(data):
    """Converts structured JSON financial data into highly descriptive text for embedding."""
    company = data.get('company_name', 'Unknown Company')
    cik = data.get('cik', 'Unknown CIK')
    date = data.get('latest_period_end_date', 'Unknown Date')
    form = data.get('form_type', 'SEC filing')
    filed_date = data.get('filed_date', 'Unknown Date')
    
    text_blocks = [
        f"Financial Numerical Data for {company} (CIK: {cik}). "
        f"This data is from their {form} filed on {filed_date}, for the period ending {date}:"
    ]
    
    sections = [
        ('Income Statement Metrics', data.get('income_statement', {})),
        ('Balance Sheet Metrics', data.get('balance_sheet', {}))
    ]
    
    for section_name, section_data in sections:
        if not section_data:
            continue
            
        text_blocks.append(f"\n{section_name}:")
        
        for metric, vals in section_data.items():
            curr_obj = vals.get('current', {})
            prior_obj = vals.get('prior', {})
            
            # Get values
            curr_val = curr_obj.get('val', 'N/A')
            prior_val = prior_obj.get('val', 'N/A')
            
            # Get Fiscal Year and Period context (e.g., "Q3 2025")
            curr_period = f"{curr_obj.get('fp', '')} {curr_obj.get('fy', '')}".strip()
            prior_period = f"{prior_obj.get('fp', '')} {prior_obj.get('fy', '')}".strip()
            
            # Format YoY as a percentage with "increase/decrease" language
            yoy = vals.get('yoy_percent_change', 'N/A')
            if isinstance(yoy, (int, float)):
                direction = "increase" if yoy > 0 else "decrease"
                yoy_str = f"{abs(yoy) * 100:.2f}% {direction}"
            else:
                yoy_str = str(yoy)
                
            metric_name = metric.replace('_', ' ').title()
            
            # Construct the highly detailed sentence
            sentence = (f"- {metric_name}: The current value for {curr_period} was {curr_val}. "
                        f"The prior period value for {prior_period} was {prior_val}. "
                        f"This represents a Year-over-Year (YoY) {yoy_str}.")
            
            text_blocks.append(sentence)
            
    return "\n".join(text_blocks)

def load_data_files():
    texts = []
    if not os.path.exists(DATA_PATH):
        print(f"Directory '{DATA_PATH}' not found. Run extraction first.")
        return ""

    for file in os.listdir(DATA_PATH):
        filepath = os.path.join(DATA_PATH, file)
        
        # Load Narrative Text
        if file.endswith(".txt"):
            with open(filepath, "r", encoding="utf-8") as f:
                texts.append(f.read())
                
        # Load Numerical JSON
        elif file.endswith(".json"):
            with open(filepath, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    text_repr = format_financial_json_to_text(data)
                    texts.append(text_repr)
                except json.JSONDecodeError:
                    print(f"Error reading JSON: {file}")
                    
    return "\n\n".join(texts)

def chunk_text(text):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    return splitter.split_text(text)

def create_vector_store(chunks):
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(chunks)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings))

    faiss.write_index(index, INDEX_PATH)

    with open(CHUNKS_PATH, "wb") as f:
        pickle.dump(chunks, f)

    print("✅ Hybrid Vector store created successfully!")

if __name__ == "__main__":
    print("Loading text and JSON files...")
    text = load_data_files()

    print("Chunking...")
    chunks = chunk_text(text)

    print("Creating embeddings + FAISS index...")
    create_vector_store(chunks)