import json
import re
import ollama
from rich.console import Console

from . import config

console = Console()

# --- Pre-routing: fast keyword checks to avoid LLM for obvious cases ---

FILING_META_PATTERNS = [
    r"when\s+(was|did)\s+.*\s+(10-[kq]|10k|10q|8-k|10-k/a|10-q/a)\s+(filed|submit)",
    r"most\s+recent\s+10-[kq]",
    r"latest\s+10-[kq]",
    r"filing\s+date\s+(of|for)\s+.*10-[kq]",
    r"date\s+.*\s+(10-[kq]|10k|10q)\s+filed",
    r"when\s+(was|did)\s+\w+\s+file\s+(a\s+)?10-[kq]",
    r"what\s+date\s+.*\s+10-[kq]",
    r"last\s+10-[kq]\s+filed",
    r"most\s+recent\s+filing",
    r"latest\s+filing\s+date",
    r"accession\s+number",
]

FILING_FORM_ALIASES = {
    "10k": "10-K", "10-k": "10-K", "10-k/a": "10-K",
    "10q": "10-Q", "10-q": "10-Q", "10-q/a": "10-Q",
    "8k": "8-K", "8-k": "8-K",
}


def _detect_filing_info_question(question):
    """Check if question is obviously about filing metadata."""
    q = question.lower()
    for pattern in FILING_META_PATTERNS:
        if re.search(pattern, q):
            return True
    return False


def _detect_xbrl_fact_question(question):
    """Check if question asks about a specific numeric fact not in standard metrics."""
    q = question.lower()
    # Specific financial line items that exist in XBRL but not in our standard metrics
    specific_fact_keywords = [
        "effective tax rate", "tax rate", "tax provision",
        "research and development", "r&d expense", "rd expense",
        "depreciation", "amortization",
        "interest expense", "interest income",
        "stock-based compensation", "share-based", "stock compensation",
        "dividends per share", "dividend per share",
        "earnings per share", "eps",
        "shares outstanding", "diluted shares",
        "goodwill", "intangible assets",
        "operating lease", "right-of-use",
        "repurchases", "buyback", "share repurchase",
        "capital expenditure", "capex",
        "working capital",
        "book value per share",
    ]
    return any(kw in q for kw in specific_fact_keywords)


def _extract_form_type(question):
    """Extract SEC form type from question."""
    q = question.lower()
    for alias, form in FILING_FORM_ALIASES.items():
        if alias in q:
            return form
    if "10-k" in q or "10k" in q or "annual report" in q:
        return "10-K"
    if "10-q" in q or "10q" in q or "quarterly" in q:
        return "10-Q"
    if "8-k" in q or "8k" in q:
        return "8-K"
    return None


def _extract_xbrl_query(question):
    """Extract what XBRL concept the user is asking about."""
    q = question.lower()

    concept_map = {
        "effective tax rate": ["effective tax rate", "tax rate", "tax provision rate", "statutory tax rate"],
        "research and development expense": ["research and development", "r&d expense", "rd expense", "r&d"],
        "depreciation": ["depreciation", "depreciation expense"],
        "amortization": ["amortization", "amortization expense"],
        "interest expense": ["interest expense"],
        "interest income": ["interest income"],
        "stock-based compensation": ["stock-based compensation", "share-based compensation", "stock compensation"],
        "dividends per share": ["dividends per share", "dividend per share"],
        "earnings per share": ["earnings per share", "eps"],
        "diluted earnings per share": ["diluted eps", "diluted earnings per share"],
        "basic earnings per share": ["basic eps", "basic earnings per share"],
        "shares outstanding": ["shares outstanding", "common shares outstanding"],
        "diluted shares outstanding": ["diluted shares", "diluted shares outstanding"],
        "goodwill": ["goodwill"],
        "intangible assets": ["intangible assets", "intangibles"],
        "operating lease right of use": ["operating lease", "right-of-use asset", "rou asset"],
        "share repurchases": ["repurchases", "buyback", "share repurchase", "stock repurchase"],
        "capital expenditure": ["capital expenditure", "capex", "capital expenditures"],
        "working capital": ["working capital"],
        "book value per share": ["book value per share"],
        "operating expenses": ["operating expenses"],
        "cost of revenue": ["cost of revenue", "cost of goods sold", "cogs"],
        "cost of goods sold": ["cost of goods sold", "cogs"],
        "gross profit": ["gross profit"],
        "operating income": ["operating income", "operating profit"],
        "net income": ["net income", "net profit", "net earnings"],
        "total revenue": ["total revenue", "total sales", "net revenue"],
        "revenue": ["revenue", "sales"],
        "total assets": ["total assets"],
        "total liabilities": ["total liabilities"],
        "stockholders equity": ["stockholders equity", "shareholders equity", "total equity"],
        "current assets": ["current assets"],
        "current liabilities": ["current liabilities"],
        "cash and equivalents": ["cash and cash equivalents", "cash equivalents", "cash"],
        "long-term debt": ["long-term debt", "long term debt", "long-term borrowings"],
    }

    for concept, keywords in concept_map.items():
        for kw in keywords:
            if kw in q:
                return concept
    return None


# --- LLM-based routing for complex cases ---

ROUTING_PROMPT_TEMPLATE = """You are a query router for a financial chatbot backed by SEC EDGAR data.

You have THREE data sources:
1. EDGAR_TOOLS_METRICS: Standard XBRL financial metrics — revenue, net income, total assets, liabilities, equity, operating income, gross profit, cash flow, margins, EPS, shares outstanding, debt, current assets/liabilities, capex. Consolidated company-wide from income/balance/cashflow statements.
2. EDGAR_TOOLS_XBRL_FACTS: Specific LINE ITEM numbers pulled from XBRL tags in the filing — effective tax rate, R&D expense, depreciation, amortization, interest expense/income, stock-based compensation, dividends per share, share buybacks, goodwill, intangible assets, cost of revenue, operating expenses. These are CONSOLIDATED COMPANY-WIDE line items that exist as XBRL tags.
3. RAG_CORPUS: Full text of 10-K/10-Q filings — MD&A, risk factors, business description, financial notes, segment breakdowns, management discussion. This is where SEGMENT and BREAKDOWN numbers live (data center revenue, iPhone revenue, cloud revenue, geographic breakdown, product line details), plus all narrative context, risk factors, and strategy.

CRITICAL DISTINCTION between XBRL_FACTS and RAG_CORPUS:
- XBRL_FACTS = consolidated line items in the financial statements (effective tax rate, R&D, depreciation) — these exist as tagged XBRL elements
- RAG_CORPUS = segment/product/geographic breakdowns (data center revenue, iPhone sales, cloud revenue) — these are ONLY in the narrative text, not standard XBRL tags

CRITICAL ROUTING RULES:
- Standard consolidated metric (revenue, net income, total assets) → "numeric"
- Consolidated line item NOT in standard metrics but exists as XBRL tag (effective tax rate, R&D expense, depreciation, interest, stock comp, dividends, shares outstanding, goodwill) → "xbrl_fact"
- SEGMENT/BREAKDOWN metric (data center revenue, iPhone sales, cloud revenue, gaming revenue, geographic revenue, product line breakdown) → "hybrid" (number is in filing text)
- Filing metadata (when was 10-Q filed, latest filing date, accession number) → "filing_info"
- Strategy, risks, business description only → "qualitative"
- Requires numbers AND context (financial health, pros/cons, analysis) → "hybrid"

Also extract:
- ticker symbol
- the specific metric or concept being asked about

Respond ONLY with valid JSON:
{{"route": "numeric|xbrl_fact|qualitative|hybrid|filing_info", "ticker": "TICKER_OR_NULL", "metric": "metric_name_or_null", "reason": "brief explanation"}}

User question: {question}
"""


def classify_query(question):
    """Route a question to the appropriate data source."""
    # Fast pre-routing: filing metadata (no LLM needed)
    if _detect_filing_info_question(question):
        ticker = extract_ticker_from_question(question)
        form_type = _extract_form_type(question) or "10-Q"
        console.print(f"[dim]Route: filing_info (pre-routed), Ticker: {ticker}, Form: {form_type}[/dim]")
        return "filing_info", ticker, form_type

    # Fast pre-routing: specific XBRL fact questions (no LLM needed)
    if _detect_xbrl_fact_question(question):
        ticker = extract_ticker_from_question(question)
        xbrl_query = _extract_xbrl_query(question)
        if xbrl_query:
            console.print(f"[dim]Route: xbrl_fact (pre-routed), Ticker: {ticker}, Query: {xbrl_query}[/dim]")
            return "xbrl_fact", ticker, xbrl_query

    # LLM routing for complex cases
    prompt = ROUTING_PROMPT_TEMPLATE.format(question=question)
    try:
        response = ollama.chat(
            model=config.OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            format="json",
        )
        result = json.loads(response["message"]["content"])
        route = result.get("route", "hybrid")
        ticker = result.get("ticker")
        metric = result.get("metric")
        reason = result.get("reason", "")
        console.print(f"[dim]Route: {route}, Ticker: {ticker}, Metric: {metric} | {reason}[/dim]")
        return route, ticker, metric
    except Exception as e:
        console.print(f"[yellow]Routing error: {e}. Defaulting to hybrid.[/yellow]")
        return "hybrid", None, None


# --- Utility functions ---

METRIC_KEYWORDS = {
    "revenue": ["revenue", "sales", "total revenue", "net sales"],
    "net_income": ["net income", "profit", "earnings", "bottom line", "net profit"],
    "operating_income": ["operating income", "operating profit", "ebit"],
    "gross_profit": ["gross profit", "gross margin"],
    "total_assets": ["total assets", "assets"],
    "total_liabilities": ["total liabilities", "liabilities", "debt"],
    "stockholders_equity": ["equity", "shareholders equity", "book value"],
    "operating_cash_flow": ["operating cash flow", "cash from operations"],
    "free_cash_flow": ["free cash flow", "fcf"],
    "current_ratio": ["current ratio"],
    "debt_to_equity": ["debt to equity", "debt-to-equity", "d/e ratio"],
    "roe": ["return on equity", "roe"],
    "net_margin": ["net margin", "profit margin", "net profit margin"],
    "operating_margin": ["operating margin"],
}

SEGMENT_KEYWORDS = [
    "data center", "iphone", "mac", "ipad", "wearables", "services",
    "cloud", "gaming", "advertising", "subscription",
    "segment", "breakdown", "by region", "by product", "by geography",
    "americas", "europe", "asia", "china", "japan",
    "hardware", "software", "licensing",
]


def is_segment_question(question):
    q_lower = question.lower()
    return any(kw in q_lower for kw in SEGMENT_KEYWORDS)


def extract_metric_from_question(question):
    q_lower = question.lower()
    for metric, keywords in METRIC_KEYWORDS.items():
        for kw in keywords:
            if kw in q_lower:
                return metric
    return None


def extract_ticker_from_question(question):
    words = question.split()
    known_tickers = {
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "TSLA", "NVDA", "META", "NFLX",
        "AMD", "INTC", "CRM", "ORCL", "IBM", "CSCO", "ADBE", "PYPL", "SQ",
        "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "BRK", "BRK-A", "BRK.B",
        "JNJ", "PFE", "UNH", "ABBV", "MRK", "TMO", "ABT", "DHR",
        "XOM", "CVX", "COP", "SLB",
        "PG", "KO", "PEP", "WMT", "COST", "HD", "MCD", "NKE",
        "DIS", "CMCSA", "T", "VZ",
        "CAT", "BA", "HON", "UPS", "RTX", "LMT", "GE",
        "PLTR", "SNOW", "COIN", "RIVN", "SOFI", "HOOD",
        "SPY", "QQQ", "IWM",
    }

    ticker_aliases = {
        "APPLE": "AAPL", "MICROSOFT": "MSFT", "GOOGLE": "GOOGL", "ALPHABET": "GOOGL",
        "AMAZON": "AMZN", "TESLA": "TSLA", "NVIDIA": "NVDA", "META": "META",
        "FACEBOOK": "META", "NETFLIX": "NFLX", "BRK": "BRK-A", "BERKSHIRE": "BRK-A",
        "SALESFORCE": "CRM", "ORACLE": "ORCL", "INTEL": "INTC", "AMD": "AMD",
        "ADOBE": "ADBE", "PAYPAL": "PYPL", "SQUARE": "SQ", "BLOCK": "SQ",
        "JPMORGAN": "JPM", "JP MORGAN": "JPM", "GOLDMAN": "GS", "VISA": "V",
        "MASTERCARD": "MA", "JOHNSON": "JNJ", "PROCTER": "PG", "COCA": "KO",
        "PEPSI": "PEP", "WALMART": "WMT", "COSTCO": "COST", "HOME DEPOT": "HD",
        "MCDONALD": "MCD", "NIKE": "NKE", "DISNEY": "DIS", "CAT": "CAT",
        "BOEING": "BA", "HONEYWELL": "HON", "UPS": "UPS", "LOCKHEED": "LMT",
        "PALANTIR": "PLTR", "SNOWFLAKE": "SNOW", "COINBASE": "COIN",
        "NIO": "NIO", "RIVIAN": "RIVN", "SOFI": "SOFI", "HOOD": "HOOD",
        "UNITEDHEALTH": "UNH", "ABBOTT": "ABT", "DANAHER": "DHR",
        "EXXON": "XOM", "CHEVRON": "CVX", "COP": "COP",
        "CISCO": "CSCO", "IBM": "IBM", "GE": "GE", "RTX": "RTX",
        "APPL": "AAPL", "MSFT": "MSFT", "GOOGL": "GOOGL", "AMZN": "AMZN",
        "TSLA": "TSLA", "NVDA": "NVDA", "META": "META", "NFLX": "NFLX",
    }

    for word in words:
        cleaned = word.strip(".,!?;:").upper()
        if cleaned in known_tickers:
            return cleaned

    q_upper = question.upper()
    for alias, ticker in ticker_aliases.items():
        if alias in q_upper:
            return ticker

    for word in words:
        cleaned = word.strip(".,!?;:").upper()
        if cleaned.isalpha() and 2 <= len(cleaned) <= 5 and cleaned in known_tickers:
            return cleaned

    return None
