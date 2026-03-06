from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer

from arxiv_coffee.config import loadConfig, loadInterests
from arxiv_coffee.copilot_auth import checkLlmAuth, runDeviceFlow
from arxiv_coffee.models import AppConfig, Paper, readPapersJsonl, writePapersJsonl

app = typer.Typer(
    help="Browse, filter, and summarize arXiv papers using AI.",
    no_args_is_help=False,
    invoke_without_command=True,
)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _loadAppConfig(config_path: Path | None) -> AppConfig:
    """Load config from file, or defaults when the file is absent."""
    return loadConfig(config_path)


def _err(msg: str) -> None:
    """Print a message to stderr."""
    print(msg, file=sys.stderr)


def _ensureAuth(config: AppConfig) -> None:
    """Check LLM auth and run Copilot device flow if needed.

    Exits with code 1 when auth cannot be established (e.g. missing
    API key for a non-Copilot model).
    """
    ready, reason = checkLlmAuth(config.model, config.api_key)
    if ready:
        return

    if reason == "no_api_key":
        _err("Error: No API key configured. Set llm.api_key in config.toml.")
        raise typer.Exit(1)

    if reason == "copilot_auth_needed":
        _err("GitHub Copilot authentication required.")
        _err("Starting device flow...")

        async def _auth() -> None:
            user_code, verification_uri, poll_task = await runDeviceFlow()
            _err(f"Open {verification_uri} and enter code: {user_code}")
            try:
                await poll_task
                _err("Authentication successful.")
            except Exception as exc:
                _err(f"Authentication failed: {exc}")
                raise typer.Exit(1) from exc

        asyncio.run(_auth())


# -------------------------------------------------------------------
# Common options
# -------------------------------------------------------------------

ConfigOption = typer.Option(
    None,
    "--config",
    "-c",
    help="Path to config.toml. Defaults to ~/.config/arxiv-coffee/config.toml.",
)


# -------------------------------------------------------------------
# Default: launch TUI
# -------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Launch the TUI when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        from arxiv_coffee.app import run

        run()


# -------------------------------------------------------------------
# Subcommand: tui
# -------------------------------------------------------------------


@app.command()
def tui() -> None:
    """Launch the interactive TUI."""
    from arxiv_coffee.app import run

    run()


# -------------------------------------------------------------------
# Subcommand: feed
# -------------------------------------------------------------------


@app.command()
def feed(
    category: list[str] = typer.Option(
        [],
        "--category",
        "-C",
        help="arXiv category (repeatable). Defaults to config value.",
    ),
    max_papers: int = typer.Option(
        0,
        "--max-papers",
        "-n",
        help="Maximum number of papers to fetch. 0 = use config value.",
    ),
    include_cross_posts: bool = typer.Option(
        False,
        "--cross-posts",
        help="Include cross-posted papers.",
    ),
    start: str = typer.Option(
        "",
        "--start",
        help="Start date (YYYY-MM-DD) for a date range query.",
    ),
    end: str = typer.Option(
        "",
        "--end",
        help="End date (YYYY-MM-DD) for a date range query.",
    ),
    config_path: Path | None = ConfigOption,
) -> None:
    """Fetch papers from arXiv and write them to stdout as JSON Lines.

    By default fetches the latest announcement window.  Pass --start
    and --end to query a specific date range instead.
    """
    config = _loadAppConfig(config_path)

    cats = category if category else None
    limit = max_papers if max_papers > 0 else None
    cross = include_cross_posts or config.include_cross_posts

    async def _run() -> list[Paper]:
        if start and end:
            from arxiv_coffee.arxiv_client import (
                fetchPapersByDateRange,
                parseFetchInputs,
            )

            req = parseFetchInputs(
                category=",".join(cats) if cats else "",
                max_papers_str=str(limit) if limit else str(config.max_papers),
                use_dates=True,
                include_cross_posts=cross,
                start_str=start,
                end_str=end,
                config=config,
            )
            return await fetchPapersByDateRange(
                config,
                req.start,  # type: ignore[arg-type]
                req.end,  # type: ignore[arg-type]
                categories=req.categories,
                max_results=req.max_papers,
                include_cross_posts=req.include_cross_posts,
            )
        else:
            from arxiv_coffee.arxiv_client import fetchLatestPapers

            return await fetchLatestPapers(
                config,
                categories=cats,
                max_results=limit,
                include_cross_posts=cross,
            )

    try:
        papers = asyncio.run(_run())
    except ValueError as exc:
        _err(f"Error: {exc}")
        raise typer.Exit(1) from exc

    _err(f"Fetched {len(papers)} papers")
    writePapersJsonl(papers)


# -------------------------------------------------------------------
# Subcommand: rate
# -------------------------------------------------------------------


@app.command()
def rate(
    min_score: float = typer.Option(
        0.0,
        "--min-score",
        "-m",
        help="Only output papers with relevance score >= this value.",
    ),
    model: str = typer.Option(
        "",
        "--model",
        help="Override the LLM model from config.",
    ),
    config_path: Path | None = ConfigOption,
) -> None:
    """Read papers from stdin, rate by relevance, write rated papers to stdout.

    Uses the configured LLM and your interests file to assign each paper
    a relevance score (0-10) and a brief reason.  Papers are written to
    stdout as JSON Lines, sorted by descending score.
    """
    if sys.stdin.isatty():
        _err("Error: No input. Pipe papers from 'arxiv-coffee feed'.")
        _err("Example: arxiv-coffee feed | arxiv-coffee rate")
        raise typer.Exit(1)

    config = _loadAppConfig(config_path)
    if model:
        config.model = model

    _ensureAuth(config)

    interests = loadInterests(config)
    if not interests:
        _err(
            "Warning: No interests file found at "
            f"{config.interests_file}. Rating without interests context."
        )
        interests = "General scientific interest."

    papers = readPapersJsonl()
    if not papers:
        _err("No papers on stdin.")
        raise typer.Exit(0)

    _err(f"Rating {len(papers)} papers...")

    def _onBatchDone(done: int, total: int) -> None:
        _err(f"  batch {done}/{total}")

    async def _run() -> list[Paper]:
        from arxiv_coffee.llm import filterPapersByRelevance

        return await filterPapersByRelevance(
            papers,
            interests,
            config,
            on_batch_done=_onBatchDone,
        )

    try:
        rated = asyncio.run(_run())
    except ValueError as exc:
        _err(f"Error: {exc}")
        raise typer.Exit(1) from exc

    if min_score > 0:
        rated = [p for p in rated if (p.relevance_score or 0) >= min_score]

    _err(f"Rated {len(papers)} papers, {len(rated)} pass threshold {min_score}")
    writePapersJsonl(rated)


# -------------------------------------------------------------------
# Subcommand: summarize
# -------------------------------------------------------------------


@app.command()
def summarize(
    model: str = typer.Option(
        "",
        "--model",
        help="Override the LLM model from config.",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Override the output directory from config.",
    ),
    config_path: Path | None = ConfigOption,
) -> None:
    """Read papers from stdin, download PDFs, summarize, and save to library.

    Each paper is downloaded, its text extracted, and an AI summary is
    generated and saved as a markdown file.  The same papers are written
    to stdout (as JSON Lines) so the pipeline can continue.
    """
    if sys.stdin.isatty():
        _err("Error: No input. Pipe papers from 'arxiv-coffee rate'.")
        _err("Example: arxiv-coffee feed | arxiv-coffee rate | arxiv-coffee summarize")
        raise typer.Exit(1)

    config = _loadAppConfig(config_path)
    if model:
        config.model = model
    if output_dir:
        config.output_dir = output_dir

    _ensureAuth(config)

    papers = readPapersJsonl()
    if not papers:
        _err("No papers on stdin.")
        raise typer.Exit(0)

    _err(f"Summarizing {len(papers)} papers...")

    def _onProgress(progress: object) -> None:
        # Import here to avoid circular dependency at module level
        _err(
            f"  downloading={progress.downloading} "  # type: ignore[attr-defined]
            f"summarizing={progress.summarizing} "  # type: ignore[attr-defined]
            f"done={progress.done}/{progress.total}"  # type: ignore[attr-defined]
        )

    async def _run() -> object:
        from arxiv_coffee.summarize_pipeline import summarizePapers

        return await summarizePapers(
            papers,
            config,
            on_progress=_onProgress,
        )

    result = asyncio.run(_run())
    _err(result.summary)  # type: ignore[attr-defined]

    # Pass papers through so the pipeline can continue (e.g. to mail)
    writePapersJsonl(papers)


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------


def runCli() -> None:
    """Top-level entry point for the ``arxiv-coffee`` command."""
    app()
