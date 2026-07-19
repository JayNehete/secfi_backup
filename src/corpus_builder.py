import re
from edgar import Company, set_identity
from rich.console import Console

from . import config

console = Console()


def _init_identity():
    set_identity(config.EDGAR_IDENTITY)


def _chunk_text(text, chunk_size=config.CHUNK_SIZE, overlap=config.CHUNK_OVERLAP):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def _extract_section_text(tenk_obj, item_code, item_name):
    try:
        report = tenk_obj.get_report(item_code)
        if report and hasattr(report, "text"):
            return report.text
    except Exception:
        pass

    try:
        item = tenk_obj[item_code]
        if item:
            return str(item)
    except Exception:
        pass

    return None


def build_corpus(ticker):
    _init_identity()
    company = Company(ticker)
    ticker_upper = ticker.upper()
    console.print(f"[bold]Building corpus for {ticker_upper}...[/bold]")

    documents = []
    metadatas = []
    ids = []

    chunk_id = 0

    # --- 10-K sections ---
    try:
        tenk_filings = company.get_filings(form="10-K").filter(amendments=False).head(2)
        for filing in tenk_filings:
            tenk = filing.obj()
            filing_date = str(filing.filing_date)
            period = str(filing.period_of_report) if hasattr(filing, "period_of_report") else filing_date

            sections = {
                "Item 1": "Business Description",
                "Item 1A": "Risk Factors",
                "Item 7": "Management Discussion and Analysis",
            }

            for item_code, section_name in sections.items():
                text = _extract_section_text(tenk, item_code, section_name)
                if text:
                    chunks = _chunk_text(text)
                    for c in chunks:
                        documents.append(c)
                        metadatas.append({
                            "ticker": ticker_upper,
                            "filing_type": "10-K",
                            "section": section_name,
                            "filing_date": filing_date,
                            "period": period,
                        })
                        ids.append(f"{ticker_upper}_10K_{section_name.replace(' ', '_')}_{chunk_id}")
                        chunk_id += 1
                    console.print(f"  [green]10-K {section_name}: {len(chunks)} chunks[/green]")

            # Notes
            try:
                notes = tenk.notes
                if notes:
                    md = notes.to_markdown()
                    if md:
                        chunks = _chunk_text(md)
                        for c in chunks:
                            documents.append(c)
                            metadatas.append({
                                "ticker": ticker_upper,
                                "filing_type": "10-K",
                                "section": "Financial Notes",
                                "filing_date": filing_date,
                                "period": period,
                            })
                            ids.append(f"{ticker_upper}_10K_Notes_{chunk_id}")
                            chunk_id += 1
                        console.print(f"  [green]10-K Notes: {len(chunks)} chunks[/green]")
            except Exception:
                pass

            # Financial statements as markdown
            try:
                financials = tenk.financials
                if financials:
                    for stmt_name, stmt_method in [
                        ("Income Statement", "income_statement"),
                        ("Balance Sheet", "balance_sheet"),
                        ("Cash Flow Statement", "cashflow_statement"),
                    ]:
                        try:
                            stmt = getattr(financials, stmt_method, None)
                            if stmt:
                                md = stmt.to_markdown()
                                if md:
                                    chunks = _chunk_text(md)
                                    for c in chunks:
                                        documents.append(c)
                                        metadatas.append({
                                            "ticker": ticker_upper,
                                            "filing_type": "10-K",
                                            "section": f"Financial - {stmt_name}",
                                            "filing_date": filing_date,
                                            "period": period,
                                        })
                                        ids.append(f"{ticker_upper}_10K_{stmt_name.replace(' ', '_')}_{chunk_id}")
                                        chunk_id += 1
                                    console.print(f"  [green]10-K {stmt_name}: {len(chunks)} chunks[/green]")
                        except Exception:
                            pass
            except Exception:
                pass

    except Exception as e:
        console.print(f"  [yellow]Error processing 10-K: {e}[/yellow]")

    # --- 10-Q sections ---
    try:
        tenq_filings = company.get_filings(form="10-Q").filter(amendments=False).head(2)
        for filing in tenq_filings:
            tenq = filing.obj()
            filing_date = str(filing.filing_date)
            period = str(filing.period_of_report) if hasattr(filing, "period_of_report") else filing_date

            sections = {
                "Item 2": "MD&A",
                "Item 1A": "Risk Factors",
            }

            for item_code, section_name in sections.items():
                text = _extract_section_text(tenq, item_code, section_name)
                if text:
                    chunks = _chunk_text(text)
                    for c in chunks:
                        documents.append(c)
                        metadatas.append({
                            "ticker": ticker_upper,
                            "filing_type": "10-Q",
                            "section": section_name,
                            "filing_date": filing_date,
                            "period": period,
                        })
                        ids.append(f"{ticker_upper}_10Q_{section_name.replace(' ', '_')}_{chunk_id}")
                        chunk_id += 1
                    console.print(f"  [green]10-Q {section_name}: {len(chunks)} chunks[/green]")

            # 10-Q financial statements
            try:
                financials = tenq.financials
                if financials:
                    for stmt_name, stmt_method in [
                        ("Income Statement", "income_statement"),
                        ("Balance Sheet", "balance_sheet"),
                        ("Cash Flow Statement", "cashflow_statement"),
                    ]:
                        try:
                            stmt = getattr(financials, stmt_method, None)
                            if stmt:
                                md = stmt.to_markdown()
                                if md:
                                    chunks = _chunk_text(md)
                                    for c in chunks:
                                        documents.append(c)
                                        metadatas.append({
                                            "ticker": ticker_upper,
                                            "filing_type": "10-Q",
                                            "section": f"Financial - {stmt_name}",
                                            "filing_date": filing_date,
                                            "period": period,
                                        })
                                        ids.append(f"{ticker_upper}_10Q_{stmt_name.replace(' ', '_')}_{chunk_id}")
                                        chunk_id += 1
                                    console.print(f"  [green]10-Q {stmt_name}: {len(chunks)} chunks[/green]")
                        except Exception:
                            pass
            except Exception:
                pass

    except Exception as e:
        console.print(f"  [yellow]Error processing 10-Q: {e}[/yellow]")

    console.print(f"\n[bold green]Corpus built: {len(documents)} chunks total for {ticker_upper}[/bold green]")
    return documents, metadatas, ids
