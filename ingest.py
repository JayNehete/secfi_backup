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
    
    text_blocks = []
    
    sections = [
        ('Income Statement', data.get('income_statement', {})),
        ('Balance Sheet', data.get('balance_sheet', {}))
    ]
    
    for section_name, section_data in sections:
        if not section_data:
            continue
            
        for metric, vals in section_data.items():
            curr_obj = vals.get('current') or {}
            prior_obj = vals.get('prior') or {}
            
            curr_val = curr_obj.get('val', 'N/A')
            prior_val = prior_obj.get('val', 'N/A')
            
            curr_period = f"{curr_obj.get('fp', '')} {curr_obj.get('fy', '')}".strip() or "the current period"
            prior_period = f"{prior_obj.get('fp', '')} {prior_obj.get('fy', '')}".strip() or "the prior period"
            
            yoy = vals.get('yoy_percent_change')
            if isinstance(yoy, (int, float)):
                direction = "increase" if yoy > 0 else "decrease"
                yoy_str = f"{abs(yoy) * 100:.2f}% {direction}"
            else:
                yoy_str = "N/A"
                
            metric_name = metric.replace('_', ' ').title()
            
            # THE FIX: Inject Company, Form, and Date into EVERY sentence so chunks are never orphaned.
            sentence = (
                f"For {company} (CIK: {cik}) in their {form} filing for the period ending {date}, "
                f"the {section_name} shows {metric_name} was {curr_val} for {curr_period}. "
                f"Compared to the prior period ({prior_period}) value of {prior_val}, "
                f"this is a Year-over-Year (YoY) {yoy_str}."
            )
            
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