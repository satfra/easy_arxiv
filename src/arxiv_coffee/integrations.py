from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


def isObsidianInstalled() -> bool:
    """Return True if Obsidian appears to be installed."""
    if shutil.which("obsidian"):
        return True
    if sys.platform == "darwin":
        return Path("/Applications/Obsidian.app").exists()
    return False


def openInObsidian(vault_path: Path) -> None:
    """Open a directory as an Obsidian vault via the obsidian:// URI scheme."""
    uri = f"obsidian://open?path={quote(str(vault_path.resolve()), safe='')}"
    if sys.platform == "darwin":
        subprocess.Popen(["open", uri])
    elif sys.platform == "win32":
        import os

        os.startfile(uri)  # type: ignore[attr-defined]  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", uri])
