import ollama
from rich.console import Console

from . import config

console = Console()

SYSTEM_PROMPT = """You are a financial analyst chatbot. You answer questions about publicly traded companies using SEC filing data.

CRITICAL RULES:
1. NEVER fabricate or guess financial numbers. Only use the data provided to you.
2. If a number is not in the provided data, say "I don't have that specific data point."
3. When citing numbers, always include the period/quarter they refer to.
4. Format large numbers with commas (e.g., $391,035,000,000 or $391.0B).
5. When year-over-year changes are provided, explain the trend clearly.
6. Be concise but thorough. Use bullet points for clarity.
7. If the user asks about a metric and you have the calculation, show the math.
"""


def generate_numeric_answer(question, metrics, yoy_changes=None):
    context_parts = []
    context_parts.append("## Available Financial Data\n")

    if metrics:
        context_parts.append("### Key Metrics (Latest Filing)\n")
        for key, value in metrics.items():
            if isinstance(value, float):
                if abs(value) >= 1_000_000_000:
                    context_parts.append(f"- {key}: ${value:,.0f} (${value/1_000_000_000:.1f}B)")
                elif abs(value) >= 1_000_000:
                    context_parts.append(f"- {key}: ${value:,.0f} (${value/1_000_000:.1f}M)")
                elif abs(value) < 1:
                    context_parts.append(f"- {key}: {value:.2%}")
                else:
                    context_parts.append(f"- {key}: {value:,.2f}")
            else:
                context_parts.append(f"- {key}: {value}")

    if yoy_changes:
        context_parts.append("\n### Year-over-Year Changes\n")
        for concept, data in yoy_changes.items():
            context_parts.append(
                f"- {concept}: {data['yoy_change_pct']:+.1f}% "
                f"(from ${data['prior_value']:,.0f} to ${data['latest_value']:,.0f}, "
                f"periods: {data['prior_period']} -> {data['latest_period']})"
            )

    context = "\n".join(context_parts)
    return _call_llm(question, context)


def generate_rag_answer(question, rag_chunks):
    context_parts = []
    context_parts.append("## Retrieved Information from SEC Filings\n")

    for i, chunk in enumerate(rag_chunks):
        meta = chunk.get("metadata", {})
        score = chunk.get("relevance_score")
        score_str = f" (relevance: {score:.2f})" if score else ""
        context_parts.append(
            f"### Source {i+1}: {meta.get('section', 'Unknown')} "
            f"({meta.get('filing_type', 'Unknown')}, {meta.get('period', 'Unknown')}){score_str}\n"
        )
        context_parts.append(chunk["text"][:2000])
        context_parts.append("")

    context = "\n".join(context_parts)
    return _call_llm(question, context)


def generate_hybrid_answer(question, metrics, yoy_changes=None, rag_chunks=None):
    context_parts = []

    if metrics:
        context_parts.append("## Financial Metrics\n")
        for key, value in metrics.items():
            if isinstance(value, float):
                if abs(value) >= 1_000_000_000:
                    context_parts.append(f"- {key}: ${value:,.0f} (${value/1_000_000_000:.1f}B)")
                elif abs(value) >= 1_000_000:
                    context_parts.append(f"- {key}: ${value:,.0f} (${value/1_000_000:.1f}M)")
                elif abs(value) < 1:
                    context_parts.append(f"- {key}: {value:.2%}")
                else:
                    context_parts.append(f"- {key}: {value:,.2f}")
            else:
                context_parts.append(f"- {key}: {value}")

    if yoy_changes:
        context_parts.append("\n## Year-over-Year Changes\n")
        for concept, data in yoy_changes.items():
            context_parts.append(
                f"- {concept}: {data['yoy_change_pct']:+.1f}% "
                f"(from ${data['prior_value']:,.0f} to ${data['latest_value']:,.0f})"
            )

    if rag_chunks:
        context_parts.append("\n## Qualitative Information from SEC Filings\n")
        for i, chunk in enumerate(rag_chunks):
            meta = chunk.get("metadata", {})
            context_parts.append(
                f"### {meta.get('section', 'Unknown')} ({meta.get('filing_type', 'Unknown')})\n"
            )
            context_parts.append(chunk["text"][:1500])
            context_parts.append("")

    context = "\n".join(context_parts)
    return _call_llm(question, context)


SUMMARY_SYSTEM_PROMPT = """You are a senior financial analyst. You produce executive-level summaries of publicly traded companies based on SEC filing data.

Your summary MUST follow this exact structure:

## Company Overview
One sentence: what the company does and its industry.

## Financial Snapshot
Key metrics table (revenue, net income, margins, assets, etc.) with the latest values.

## Year-over-Year Performance
Bullet points for each major metric showing the YoY % change and what it means.

## Key Strengths
2-4 bullet points — what the company is doing well financially.

## Key Risks / Concerns
2-4 bullet points — what could go wrong, based on risk factors and financial red flags.

## Bottom Line
1-2 sentence verdict: is this company on a healthy trajectory?

RULES:
- Use ONLY the data provided. Never fabricate numbers.
- Be direct and concise. No filler sentences.
- Flag any concerning ratios (e.g., current ratio < 1, negative equity, declining revenue).
"""


def generate_summary(ticker, metrics, yoy_changes=None, rag_chunks=None):
    context_parts = []
    context_parts.append(f"# {ticker} - Full Data Package for Summary\n")

    if metrics:
        context_parts.append("## Key Financial Metrics\n")
        for key, value in metrics.items():
            if isinstance(value, float):
                if abs(value) >= 1_000_000_000:
                    context_parts.append(f"- {key}: ${value:,.0f} (${value/1_000_000_000:.1f}B)")
                elif abs(value) >= 1_000_000:
                    context_parts.append(f"- {key}: ${value:,.0f} (${value/1_000_000:.1f}M)")
                elif abs(value) < 1:
                    context_parts.append(f"- {key}: {value:.2%}")
                else:
                    context_parts.append(f"- {key}: {value:,.2f}")
            elif value is not None:
                context_parts.append(f"- {key}: {value}")

    if yoy_changes:
        context_parts.append("\n## Year-over-Year Changes\n")
        for concept, data in yoy_changes.items():
            context_parts.append(
                f"- {concept}: {data['yoy_change_pct']:+.1f}% "
                f"(from ${data['prior_value']:,.0f} to ${data['latest_value']:,.0f})"
            )

    if rag_chunks:
        context_parts.append("\n## Key Qualitative Information from SEC Filings\n")
        seen = set()
        for chunk in rag_chunks:
            meta = chunk.get("metadata", {})
            section = meta.get("section", "Unknown")
            if section in seen:
                continue
            seen.add(section)
            context_parts.append(f"### {section} ({meta.get('filing_type', '')})\n")
            context_parts.append(chunk["text"][:1500])
            context_parts.append("")

    context = "\n".join(context_parts)

    try:
        response = ollama.chat(
            model=config.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Generate a comprehensive executive summary for {ticker} using the following data:\n\n{context}"},
            ],
        )
        return response["message"]["content"]
    except Exception as e:
        return f"Error generating summary: {e}"


def generate_filing_info_answer(question, filing_metadata_list):
    """Generate answer about filing metadata (dates, accession numbers, etc.)."""
    if not filing_metadata_list:
        return "No filing information found. The company may not have any filings of that type."

    context_parts = []
    context_parts.append("## Filing Information\n")
    for i, meta in enumerate(filing_metadata_list):
        context_parts.append(f"### Filing {i+1}\n")
        context_parts.append(f"- Form: {meta.get('form', 'Unknown')}")
        context_parts.append(f"- Filing Date: {meta.get('filing_date', 'Unknown')}")
        if meta.get('period_of_report'):
            context_parts.append(f"- Period of Report: {meta['period_of_report']}")
        if meta.get('accession_no'):
            context_parts.append(f"- Accession Number: {meta['accession_no']}")
        context_parts.append("")

    context = "\n".join(context_parts)

    try:
        response = ollama.chat(
            model=config.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Answer the following question using ONLY the provided filing data.\n\nQuestion: {question}\n\n{context}\n\nProvide a direct, factual answer. Include the exact date."},
            ],
        )
        return response["message"]["content"]
    except Exception as e:
        return f"Error generating response: {e}"


def generate_xbrl_fact_answer(question, xbrl_facts):
    """Generate answer about specific XBRL facts from filings."""
    if not xbrl_facts:
        return "No matching XBRL facts found in the filings for this query."

    # Filter out facts with NaN/None values
    valid_facts = [f for f in xbrl_facts if f.get("value") is not None]
    try:
        valid_facts = [f for f in valid_facts if not (isinstance(f["value"], float) and f["value"] != f["value"])]
    except Exception:
        pass

    if not valid_facts:
        return "No valid numerical XBRL facts found for this query."

    context_parts = []
    context_parts.append("## XBRL Facts Found\n")
    for fact in valid_facts:
        value = fact.get("value")
        unit = fact.get("unit", "")
        period = fact.get("period", "")
        label = fact.get("label", fact.get("concept", ""))
        form = fact.get("form_type", "")
        filing_date = fact.get("filing_date", "")

        if value is not None:
            if isinstance(value, (int, float)):
                if unit and "USD" in unit.upper():
                    if abs(value) >= 1_000_000_000:
                        context_parts.append(f"- {label}: ${value:,.0f} (${value/1_000_000_000:.1f}B) [{period}, {form}, filed {filing_date}]")
                    elif abs(value) >= 1_000_000:
                        context_parts.append(f"- {label}: ${value:,.0f} (${value/1_000_000:.1f}M) [{period}, {form}, filed {filing_date}]")
                    else:
                        context_parts.append(f"- {label}: ${value:,.2f} [{period}, {form}, filed {filing_date}]")
                elif "%" in unit.upper() or "percent" in unit.lower() or (isinstance(value, float) and 0 < abs(value) < 1):
                    context_parts.append(f"- {label}: {value:.1%} [{period}, {form}, filed {filing_date}]")
                else:
                    context_parts.append(f"- {label}: {value:,.2f} {unit} [{period}, {form}, filed {filing_date}]")
            else:
                context_parts.append(f"- {label}: {value} [{period}, {form}, filed {filing_date}]")

    context = "\n".join(context_parts)

    try:
        response = ollama.chat(
            model=config.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Answer the following question using ONLY the provided XBRL fact data.\n\nQuestion: {question}\n\n{context}\n\nProvide a direct answer with the exact value and period. If multiple periods are available, show the most recent one prominently and note any trends."},
            ],
        )
        return response["message"]["content"]
    except Exception as e:
        return f"Error generating response: {e}"


def _call_llm(question, context):
    user_message = f"""Answer the following question using ONLY the provided data.

Question: {question}

{context}

Provide a clear, concise answer. Use specific numbers when available. If data is missing for part of the answer, acknowledge it."""

    try:
        response = ollama.chat(
            model=config.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        return response["message"]["content"]
    except Exception as e:
        return f"Error generating response: {e}"


PROSCONS_SYSTEM_PROMPT = """You are a senior equity research analyst. You produce a structured pros and cons investment analysis for a company based on SEC filing data.

You MUST follow this structure exactly:

## Pros
List 4-8 pros. Each pro MUST:
- Start with a bold label (e.g., **Strong Revenue Growth**)
- Include the specific supporting number or data point from the provided data
- Explain WHY this is a positive signal

Direction rules for pros:
- Revenue, net income, operating income, gross profit INCREASING → pro
- Healthy or improving margins → pro
- Strong positive free cash flow → pro
- Current ratio > 1.0 → pro
- Low debt-to-equity → pro
- High ROE → pro
- Positive segment growth → pro
- Revenue growth outpacing cost growth → pro

## Cons
List 4-8 cons. Each con MUST:
- Start with a bold label (e.g., **Declining Margins**)
- Include the specific supporting number or data point from the provided data
- Explain WHY this is a negative signal

Direction rules for cons:
- Revenue, net income, operating income DECREASING → con
- Declining or low margins → con
- Negative or declining free cash flow → con
- Current ratio < 1.0 → con
- High or increasing debt-to-equity → con
- Low or declining ROE → con
- Costs growing faster than revenue → con
- Risk factors from 10-K that could materially impact the business → con

## Net Assessment
One sentence: do the pros outweigh the cons, or vice versa?

RULES:
- NEVER fabricate numbers. Use ONLY the data provided.
- Every pro/con MUST have a number backing it. No vague statements.
- Direction matters: +6% revenue growth is a pro; -6% is a con.
- If a metric is ambiguous (e.g., high debt but strong cash flow), present both sides in the appropriate section.
- Be direct. No filler. Each bullet should be 1-2 sentences max.
"""


def generate_pros_cons(ticker, metrics, yoy_changes=None, rag_chunks=None):
    context_parts = []
    context_parts.append(f"# {ticker} - Full Data Package for Pros/Cons Analysis\n")

    if metrics:
        context_parts.append("## Key Financial Metrics\n")
        for key, value in metrics.items():
            if value is None:
                continue
            if isinstance(value, float):
                if abs(value) >= 1_000_000_000:
                    context_parts.append(f"- {key}: ${value:,.0f} (${value/1_000_000_000:.1f}B)")
                elif abs(value) >= 1_000_000:
                    context_parts.append(f"- {key}: ${value:,.0f} (${value/1_000_000:.1f}M)")
                elif abs(value) < 1:
                    context_parts.append(f"- {key}: {value:.2%}")
                else:
                    context_parts.append(f"- {key}: {value:,.2f}")
            else:
                context_parts.append(f"- {key}: {value}")

    if yoy_changes:
        context_parts.append("\n## Year-over-Year Changes (direction indicators)\n")
        for concept, data in yoy_changes.items():
            direction = "UP" if data["yoy_change_pct"] > 0 else "DOWN"
            context_parts.append(
                f"- {concept}: {direction} {data['yoy_change_pct']:+.1f}% "
                f"(${data['prior_value']:,.0f} -> ${data['latest_value']:,.0f})"
            )

    if rag_chunks:
        context_parts.append("\n## Filing Context (Risk Factors, MD&A, Business Description)\n")
        seen_sections = set()
        for chunk in rag_chunks:
            meta = chunk.get("metadata", {})
            section = meta.get("section", "Unknown")
            if section in seen_sections:
                continue
            seen_sections.add(section)
            context_parts.append(f"### {section} ({meta.get('filing_type', '')})\n")
            context_parts.append(chunk["text"][:2000])
            context_parts.append("")

    context = "\n".join(context_parts)

    try:
        response = ollama.chat(
            model=config.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": PROSCONS_SYSTEM_PROMPT},
                {"role": "user", "content": f"Generate a pros and cons investment analysis for {ticker}:\n\n{context}"},
            ],
        )
        return response["message"]["content"]
    except Exception as e:
        return f"Error generating pros/cons: {e}"
