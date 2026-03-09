from numerical_extractor import run_numerical_extraction
from financial_text_extractor import run_financial_text_extraction

def run_all_extractions(ingest_to_vector=False, use_crawler=False):
    print("=" * 80)
    print("SEC DATA EXTRACTION - ALL MODES WITH FILE SAVING")
    print("=" * 80)

    print("\n[1/2] Running Numerical Extraction...")
    print("-" * 80)
    numerical_results = run_numerical_extraction()

    print("\n[2/2] Running Financial Text Extraction...")

    if use_crawler:
        print("(Using EdgarCrawler library - battle-tested extraction)")
    else:
        print("(Using direct SEC.gov HTML parsing - FREE, no quotas)")

    print("-" * 80)
    financial_text_results = run_financial_text_extraction()

    print("\n" + "=" * 80)
    print("EXTRACTION COMPLETE")
    print("=" * 80)

    num_count = len(numerical_results['saved_files']) if numerical_results else 0
    num_results = len(numerical_results['results']) if numerical_results else 0
    text_count = len(financial_text_results['saved_files']) if financial_text_results else 0
    text_results_count = len(financial_text_results['results']) if financial_text_results else 0

    print(f"Numerical: {num_results} companies, {num_count} files saved")
    print(f"Financial Text: {text_results_count} companies, {text_count} files saved")

    results = {
        'numerical': numerical_results,
        'financial_text': financial_text_results
    }

    # if ingest_to_vector:
    #     print("\n" + "=" * 80)
    #     print("INGESTING TO VECTOR STORE")
    #     print("=" * 80)

    #     try:
    #         from ingest_filings import SECIngestionPipeline

    #         pipeline = SECIngestionPipeline(
    #             persist_directory='./chroma_db',
    #             embedding_model='all-MiniLM-L6-v2'
    #         )

    #         total_ingested = 0
    #         for filing_data in financial_text_results.get('results', []):
    #             added = pipeline.ingest_financial_text(filing_data)
    #             if added:
    #                 total_ingested += added

    #         print(f"\nTotal chunks ingested to vector store: {total_ingested}")

    #         stats = pipeline.get_pipeline_stats()
    #         print("\nVector Store Statistics:")
    #         print(f"  Total Documents: {stats['vector_store']['total_documents']}")
    #         print(f"  Collection: {stats['vector_store']['collection_name']}")

    #     except ImportError as e:
    #         print(f"\nERROR: Vector store not available ({e})")
    #         print("To enable vector store, install: pip install chromadb sentence-transformers numpy")
    #     except Exception as e:
    #         print(f"\nERROR during vector ingestion: {e}")

    # return results

if __name__ == "__main__":
    import sys
    ing = '--vector' in sys.argv
    crawler = '--crawler' in sys.argv
    results = run_all_extractions(ingest_to_vector=ing, use_crawler=crawler)

