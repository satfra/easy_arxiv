from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w

from arxiv_coffee.models import AppConfig

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "arxiv-coffee"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"


def loadConfig(path: Path | None = None) -> AppConfig:
    """Load configuration from a TOML file, falling back to defaults."""
    config_path = path or DEFAULT_CONFIG_PATH

    if not config_path.exists():
        return AppConfig()

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    llm = data.get("llm", {})
    arxiv = data.get("arxiv", {})
    paths = data.get("paths", {})

    return AppConfig(
        api_key=llm.get("api_key", ""),
        model=llm.get("model", "openai/gpt-4o"),
        base_url=llm.get("base_url", ""),
        requests_per_minute=llm.get("requests_per_minute", 0),
        categories=arxiv.get("categories", ["hep-ph"]),
        max_papers=arxiv.get("max_papers", 100),
        include_cross_posts=arxiv.get("include_cross_posts", False),
        interests_file=Path(
            paths.get("interests_file", str(DEFAULT_CONFIG_DIR / "interests.md"))
        ),
        output_dir=Path(
            paths.get("output_dir", str(Path.home() / "arxiv-coffee-library"))
        ),
    )


def saveConfig(config: AppConfig, path: Path | None = None) -> Path:
    """Save configuration to a TOML file. Creates parent directories if needed."""
    config_path = path or DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "llm": {
            "api_key": config.api_key,
            "model": config.model,
            "base_url": config.base_url,
            "requests_per_minute": config.requests_per_minute,
        },
        "arxiv": {
            "categories": config.categories,
            "max_papers": config.max_papers,
            "include_cross_posts": config.include_cross_posts,
        },
        "paths": {
            "interests_file": str(config.interests_file),
            "output_dir": str(config.output_dir),
        },
    }

    # Remove empty optional fields to keep the file clean
    if not data["llm"]["base_url"]:
        del data["llm"]["base_url"]
    if not data["llm"]["requests_per_minute"]:
        del data["llm"]["requests_per_minute"]

    with open(config_path, "wb") as f:
        tomli_w.dump(data, f)

    return config_path


def validateConfig(
    *,
    api_key: str,
    model: str,
    base_url: str,
    requests_per_minute: str,
    categories: str,
    max_papers: str,
    output_dir: str,
    interests_file: str,
    include_cross_posts: bool,
) -> tuple[AppConfig, list[str]]:
    """Validate raw config form values and build an AppConfig.

    Accepts raw string values (as entered by the user) and returns a
    validated AppConfig together with a list of warning messages for any
    values that were corrected to defaults.
    """
    warnings: list[str] = []

    if not api_key and not model.startswith("github_copilot/") and not model.startswith("claude_agent_sdk/"):
        warnings.append("API key is empty \u2014 AI features won't work.")

    if not model:
        warnings.append("Model is empty \u2014 using default.")
        model = "openai/gpt-4o"

    cat_list = [c.strip() for c in categories.split(",") if c.strip()]
    if not cat_list:
        warnings.append("No categories \u2014 defaulting to hep-ph.")
        cat_list = ["hep-ph"]

    try:
        max_papers_int = int(max_papers)
        if max_papers_int < 1:
            raise ValueError
    except ValueError:
        warnings.append("Invalid max papers \u2014 defaulting to 100.")
        max_papers_int = 100

    try:
        rpm = int(requests_per_minute) if requests_per_minute else 0
        if rpm < 0:
            raise ValueError
    except ValueError:
        warnings.append("Invalid requests/min \u2014 defaulting to 0 (unlimited).")
        rpm = 0

    if not output_dir:
        warnings.append("Output dir is empty \u2014 using ./output.")
        output_dir = "./output"

    if not interests_file:
        warnings.append("Interests file path is empty \u2014 using default.")
        interests_file = str(Path.home() / ".config" / "arxiv-coffee" / "interests.md")

    config = AppConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
        requests_per_minute=rpm,
        categories=cat_list,
        max_papers=max_papers_int,
        include_cross_posts=include_cross_posts,
        output_dir=Path(output_dir),
        interests_file=Path(interests_file),
    )
    return config, warnings


def loadInterests(config: AppConfig) -> str | None:
    """Load the interests file content.

    Returns the text content if the file exists and is non-empty,
    None otherwise.
    """
    if not config.interests_file.exists():
        return None
    try:
        text = config.interests_file.read_text(encoding="utf-8")
    except OSError:
        return None
    return text if text.strip() else None


def saveInterests(config: AppConfig, text: str) -> None:
    """Save text to the interests file, creating parent directories."""
    config.interests_file.parent.mkdir(parents=True, exist_ok=True)
    config.interests_file.write_text(text, encoding="utf-8")


def ensureConfigExists(path: Path | None = None) -> tuple[AppConfig, bool]:
    """Load config if it exists, otherwise create a default one.

    Returns:
      A tuple of (config, is_new) where is_new is True if a fresh
      default config was just created.
    """
    config_path = path or DEFAULT_CONFIG_PATH
    is_new = not config_path.exists()

    if is_new:
        config = AppConfig()
        saveConfig(config, config_path)
        return config, True

    return loadConfig(config_path), False
