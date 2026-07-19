import sys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from . import config
from .rag_engine import corpus_exists, build_and_store_corpus, query as rag_query
from .edgar_client import (
    get_key_metrics,
    compute_yoy_changes,
    get_financial_summary_as_markdown,
    get_notes_as_markdown,
    get_filing_sections,
    get_income_statement,
    get_balance_sheet,
    get_cashflow_statement,
    get_filing_metadata,
    search_xbrl_facts,
)
from .query_router import classify_query, extract_metric_from_question, extract_ticker_from_question
from .response_generator import (
    generate_numeric_answer,
    generate_rag_answer,
    generate_hybrid_answer,
    generate_summary,
    generate_pros_cons,
    generate_filing_info_answer,
    generate_xbrl_fact_answer,
)

console = Console()

HELP_TEXT = """
[bold cyan]SEC Financial Chatbot - Commands[/bold cyan]

  [bold]/summary[/bold]   Key insights summary (e.g., /summary AAPL)
  [bold]/proscons[/bold]  Pros and cons analysis (e.g., /proscons AAPL)
  [bold]/yoy[/bold]       Show year-over-year changes (e.g., /yoy AAPL)
  [bold]/raw[/bold]       Show raw financial data (e.g., /raw AAPL income)
  [bold]/build[/bold]     Build corpus for a company (e.g., /build AAPL)
  [bold]/help[/bold]      Show this help message
  [bold]/quit[/bold]      Exit the chatbot
"""


def ensure_corpus(ticker):
    if not corpus_exists(ticker):
        console.print(f"[yellow]First time asking about {ticker}. Building corpus (this may take a minute)...[/yellow]")
        success = build_and_store_corpus(ticker)
        if not success:
            console.print(f"[red]Failed to build corpus for {ticker}[/red]")
            return False
    return True


def handle_question(question):
    route, ticker, metric = classify_query(question)

    if not ticker:
        ticker = extract_ticker_from_question(question)

    if not ticker:
        console.print("[red]Could not identify a company ticker. Please include a ticker (e.g., AAPL, MSFT).[/red]")
        return

    ticker = ticker.upper()
    console.print(f"\n[bold]Analyzing {ticker}...[/bold]\n")

    metrics = None
    yoy = None
    rag_chunks = None

    if route == "filing_info":
        console.print("[dim]Fetching filing metadata...[/dim]")
        try:
            form_type = metric or "10-Q"
            metadata_list = get_filing_metadata(ticker, form_type=form_type, count=3)
            console.print("[dim]Generating response...[/dim]\n")
            answer = generate_filing_info_answer(question, metadata_list)
        except Exception as e:
            console.print(f"[red]Error fetching filing info: {e}[/red]")
            return
        console.print(Panel(Markdown(answer), title=f"{ticker} - Filing Info", border_style="green"))
        return

    if route == "xbrl_fact":
        console.print("[dim]Querying XBRL facts...[/dim]")
        try:
            xbrl_facts = search_xbrl_facts(ticker, metric)
            if not xbrl_facts:
                console.print("[yellow]No XBRL facts found. Falling back to hybrid search...[/yellow]")
                route = "hybrid"
            else:
                console.print("[dim]Generating response...[/dim]\n")
                answer = generate_xbrl_fact_answer(question, xbrl_facts)
                console.print(Panel(Markdown(answer), title=f"{ticker} - XBRL Fact", border_style="green"))
                return
        except Exception as e:
            console.print(f"[yellow]Error querying XBRL facts: {e}. Falling back to hybrid...[/yellow]")
            route = "hybrid"

    # Ensure corpus exists for routes that need RAG
    if not ensure_corpus(ticker):
        return

    if route in ("numeric", "hybrid"):
        console.print("[dim]Fetching financial data...[/dim]")
        try:
            metrics = get_key_metrics(ticker)
        except Exception as e:
            console.print(f"[yellow]Error fetching metrics: {e}[/yellow]")
        try:
            yoy = compute_yoy_changes(ticker)
        except Exception as e:
            console.print(f"[yellow]Error computing YoY changes: {e}[/yellow]")

    if route in ("qualitative", "hybrid"):
        console.print("[dim]Searching filing documents...[/dim]")
        try:
            rag_chunks = rag_query(ticker, question)
        except Exception as e:
            console.print(f"[yellow]Error querying RAG: {e}[/yellow]")

    console.print("[dim]Generating response...[/dim]\n")

    if route == "numeric":
        answer = generate_numeric_answer(question, metrics, yoy)
    elif route == "qualitative":
        answer = generate_rag_answer(question, rag_chunks or [])
    else:
        answer = generate_hybrid_answer(question, metrics, yoy, rag_chunks)

    console.print(Panel(Markdown(answer), title=f"{ticker} - Answer", border_style="green"))


def handle_raw_command(args):
    if len(args) < 2:
        console.print("[yellow]Usage: /raw TICKET [income|balance|cashflow|metrics|notes|sections][/yellow]")
        return

    ticker = args[0].upper()
    data_type = args[1].lower()

    if data_type == "income":
        df = get_income_statement(ticker)
        if df is not None:
            console.print(df.to_string())
        else:
            console.print("[red]No income statement data found[/red]")

    elif data_type == "balance":
        df = get_balance_sheet(ticker)
        if df is not None:
            console.print(df.to_string())
        else:
            console.print("[red]No balance sheet data found[/red]")

    elif data_type == "cashflow":
        df = get_cashflow_statement(ticker)
        if df is not None:
            console.print(df.to_string())
        else:
            console.print("[red]No cash flow data found[/red]")

    elif data_type == "metrics":
        metrics = get_key_metrics(ticker)
        if metrics:
            for k, v in metrics.items():
                console.print(f"  {k}: {v}")
        else:
            console.print("[red]No metrics found[/red]")

    elif data_type == "notes":
        md = get_notes_as_markdown(ticker)
        if md:
            console.print(Markdown(md[:3000]))
        else:
            console.print("[red]No notes found[/red]")

    elif data_type == "sections":
        sections = get_filing_sections(ticker)
        for name, text in sections.items():
            console.print(f"\n[bold]{name}[/bold]")
            console.print(text[:1000])

    else:
        console.print(f"[red]Unknown data type: {data_type}. Use income, balance, cashflow, metrics, notes, or sections[/red]")


def handle_yoy_command(args):
    if not args:
        console.print("[yellow]Usage: /yoy TICKER[/yellow]")
        return

    ticker = args[0].upper()
    yoy = compute_yoy_changes(ticker)
    if yoy:
        console.print(f"\n[bold]Year-over-Year Changes for {ticker}[/bold]\n")
        for concept, data in yoy.items():
            direction = "up" if data["yoy_change_pct"] > 0 else "down"
            console.print(
                f"  {concept}: [{'green' if data['yoy_change_pct'] > 0 else 'red'}]"
                f"{data['yoy_change_pct']:+.1f}%[/] "
                f"(${data['prior_value']:,.0f} -> ${data['latest_value']:,.0f})"
            )
    else:
        console.print("[red]No YoY data available[/red]")


def handle_summary_command(args):
    if not args:
        console.print("[yellow]Usage: /summary TICKER[/yellow]")
        return

    ticker = args[0].upper()
    console.print(f"\n[bold]Generating summary for {ticker}...[/bold]\n")

    console.print(f"[dim]Ensuring corpus for {ticker}...[/dim]")
    ensure_corpus(ticker)

    console.print("[dim]Fetching financial metrics...[/dim]")
    metrics = {}
    yoy = None
    rag_chunks = None

    try:
        metrics = get_key_metrics(ticker)
    except Exception as e:
        console.print(f"[yellow]Error fetching metrics: {e}[/yellow]")

    try:
        yoy = compute_yoy_changes(ticker)
    except Exception as e:
        console.print(f"[yellow]Error computing YoY changes: {e}[/yellow]")

    console.print("[dim]Retrieving key filing sections...[/dim]")
    try:
        rag_chunks = rag_query(ticker, f"key insights, business overview, risks, financial performance {ticker}")
    except Exception as e:
        console.print(f"[yellow]Error querying RAG: {e}[/yellow]")

    console.print("[dim]Generating summary...[/dim]\n")

    summary = generate_summary(ticker, metrics, yoy, rag_chunks)
    console.print(Panel(Markdown(summary), title=f"{ticker} - Executive Summary", border_style="cyan"))


def handle_proscons_command(args):
    if not args:
        console.print("[yellow]Usage: /proscons TICKER[/yellow]")
        return

    ticker = args[0].upper()
    console.print(f"\n[bold]Generating pros & cons analysis for {ticker}...[/bold]\n")

    console.print(f"[dim]Ensuring corpus for {ticker}...[/dim]")
    ensure_corpus(ticker)

    console.print("[dim]Fetching financial metrics...[/dim]")
    metrics = {}
    yoy = None
    rag_chunks = None

    try:
        metrics = get_key_metrics(ticker)
    except Exception as e:
        console.print(f"[yellow]Error fetching metrics: {e}[/yellow]")

    try:
        yoy = compute_yoy_changes(ticker)
    except Exception as e:
        console.print(f"[yellow]Error computing YoY changes: {e}[/yellow]")

    console.print("[dim]Retrieving risk factors, MD&A, and business context...[/dim]")
    try:
        rag_chunks = rag_query(ticker, f"risk factors, financial performance, business strengths, challenges, competition {ticker}")
    except Exception as e:
        console.print(f"[yellow]Error querying RAG: {e}[/yellow]")

    console.print("[dim]Generating pros & cons analysis...[/dim]\n")

    analysis = generate_pros_cons(ticker, metrics, yoy, rag_chunks)
    console.print(Panel(Markdown(analysis), title=f"{ticker} - Pros & Cons Analysis", border_style="yellow"))


def main():
    console.print(Panel(
        "[bold cyan]SEC Financial Chatbot[/bold cyan]\n"
        "Ask any question about a publicly traded company.\n"
        "Type /help for commands, /quit to exit.",
        border_style="blue",
    ))

    current_ticker = None

    while True:
        try:
            question = Prompt.ask("\n[bold blue]>[/bold blue]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        question = question.strip()
        if not question:
            continue

        if question.lower() in ("/quit", "/exit", "quit", "exit"):
            console.print("[dim]Goodbye![/dim]")
            break

        if question.lower() == "/help":
            console.print(HELP_TEXT)
            continue

        if question.lower().startswith("/build"):
            parts = question.split()
            if len(parts) < 2:
                console.print("[yellow]Usage: /build TICKER[/yellow]")
            else:
                ticker = parts[1].upper()
                console.print(f"[bold]Building corpus for {ticker}...[/bold]")
                build_and_store_corpus(ticker)
            continue

        if question.lower().startswith("/raw"):
            parts = question.split()
            handle_raw_command(parts[1:])
            continue

        if question.lower().startswith("/yoy"):
            parts = question.split()
            handle_yoy_command(parts[1:])
            continue

        if question.lower().startswith("/summary"):
            parts = question.split()
            handle_summary_command(parts[1:])
            continue

        if question.lower().startswith("/proscons"):
            parts = question.split()
            handle_proscons_command(parts[1:])
            continue

        handle_question(question)
