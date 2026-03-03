from __future__ import annotations

import json
import logging

import litellm

from arxiv_coffee.models import AppConfig, Paper

logger = logging.getLogger(__name__)

# Suppress litellm's noisy logging
litellm.suppress_debug_info = True

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

FILTER_SYSTEM_PROMPT = """\
You are a research assistant helping a scientist find relevant arXiv papers.
You will receive:
1. A description of the user's research interests.
2. A list of papers, each with an ID, title, and abstract.

For each paper, evaluate how relevant it is to the user's interests on a scale
from 0 (completely irrelevant) to 10 (exactly their area of research).

Respond with a JSON array. Each element must have exactly these fields:
- "id": the paper ID (string, exactly as given)
- "score": relevance score (integer, 0-10)
- "reason": a brief one-sentence explanation of why this score was given

Return ONLY the JSON array, no other text. Example:
[{"id": "2603.01234v1", "score": 8, "reason": "Directly addresses SUSY phenomenology at the LHC."}]
"""

SUMMARY_SYSTEM_PROMPT = """\
You are a scientific summarizer. You will receive the full text of an academic
paper. Produce a concise but exhaustive summary in markdown format.

Your summary should include:
1. **Motivation**: Why was this study conducted? What gap does it address?
2. **Methods**: What theoretical framework, tools, or techniques were used?
3. **Key Results**: What are the main findings? Include important numbers,
   limits, or equations where relevant.
4. **Conclusions**: What do the authors conclude? What are the implications?
5. **Outlook**: Any future directions mentioned?

Guidelines:
- Be precise and technical — the reader is a physicist.
- Use LaTeX notation for equations where helpful (e.g. $m_H = 125$ GeV).
- Keep the summary between 300-600 words.
- Do NOT include the abstract (it will be added separately).
- Use markdown headers (##) for each section.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _buildCompletionKwargs(config: AppConfig) -> dict:
    """Build common kwargs for litellm calls from config."""
    kwargs: dict = {
        "model": config.model,
        "api_key": config.api_key,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return kwargs


def _formatPapersForFilter(papers: list[Paper]) -> str:
    """Format papers into a text block for the filter prompt."""
    lines: list[str] = []
    for p in papers:
        lines.append(f"ID: {p.short_id}")
        lines.append(f"Title: {p.title}")
        lines.append(f"Abstract: {p.abstract}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def filterPapersByRelevance(
    papers: list[Paper],
    interests: str,
    config: AppConfig,
    *,
    batch_size: int = 20,
) -> list[Paper]:
    """Use an LLM to score papers by relevance to the user's interests.

    Papers are sent in batches to stay within context limits. Each paper's
    relevance_score and relevance_reason are populated. Returns all papers
    sorted by descending relevance score.
    """
    if not papers:
        return []

    if not config.api_key:
        raise ValueError("No API key configured. Set llm.api_key in config.toml.")

    kwargs = _buildCompletionKwargs(config)
    scored: dict[str, tuple[float, str]] = {}

    # Process in batches
    for i in range(0, len(papers), batch_size):
        batch = papers[i : i + batch_size]
        papers_text = _formatPapersForFilter(batch)

        user_message = (
            f"## My Research Interests\n\n{interests}\n\n"
            f"## Papers to Evaluate\n\n{papers_text}"
        )

        response = await litellm.acompletion(
            messages=[
                {"role": "system", "content": FILTER_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
            **kwargs,
        )

        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[: raw.rfind("```")]
            raw = raw.strip()

        try:
            results = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM filter response, skipping batch %d", i)
            continue

        for entry in results:
            paper_id = str(entry.get("id", ""))
            score = float(entry.get("score", 0))
            reason = str(entry.get("reason", ""))
            scored[paper_id] = (score, reason)

    # Apply scores to papers
    for paper in papers:
        if paper.short_id in scored:
            paper.relevance_score, paper.relevance_reason = scored[paper.short_id]
        else:
            paper.relevance_score = 0.0
            paper.relevance_reason = "Not evaluated"

    # Sort by score descending
    papers.sort(key=lambda p: p.relevance_score or 0.0, reverse=True)
    return papers


async def summarizePaper(
    paper: Paper,
    full_text: str,
    config: AppConfig,
    *,
    max_text_chars: int = 80_000,
) -> str:
    """Use an LLM to generate a summary of a paper from its full text.

    Returns the summary as a markdown string.
    """
    if not config.api_key:
        raise ValueError("No API key configured. Set llm.api_key in config.toml.")

    kwargs = _buildCompletionKwargs(config)

    # Truncate very long papers to stay within context limits
    text = full_text[:max_text_chars]
    if len(full_text) > max_text_chars:
        text += "\n\n[... text truncated for length ...]"

    user_message = (
        f"# {paper.title}\n\n**Authors:** {', '.join(paper.authors)}\n\n---\n\n{text}"
    )

    response = await litellm.acompletion(
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        **kwargs,
    )

    return response.choices[0].message.content.strip()
