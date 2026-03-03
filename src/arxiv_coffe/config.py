from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w

from arxiv_coffe.models import AppConfig

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "arxiv-coffe"
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
        categories=arxiv.get("categories", ["hep-ph"]),
        max_papers=arxiv.get("max_papers", 50),
        interests_file=Path(
            paths.get("interests_file", str(DEFAULT_CONFIG_DIR / "interests.md"))
        ),
        output_dir=Path(
            paths.get("output_dir", str(Path.home() / "arxiv-coffe-library"))
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
        },
        "arxiv": {
            "categories": config.categories,
            "max_papers": config.max_papers,
        },
        "paths": {
            "interests_file": str(config.interests_file),
            "output_dir": str(config.output_dir),
        },
    }

    # Remove empty optional fields to keep the file clean
    if not data["llm"]["base_url"]:
        del data["llm"]["base_url"]

    with open(config_path, "wb") as f:
        tomli_w.dump(data, f)

    return config_path


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
