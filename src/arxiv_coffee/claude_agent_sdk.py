from __future__ import annotations

import asyncio
import logging
import os
import shutil

logger = logging.getLogger(__name__)

_SDK_PREFIX = "claude_agent_sdk/"


def isClaudeAgentSdkModel(model: str) -> bool:
    """Check whether the model string uses the claude_agent_sdk/ prefix."""
    return model.startswith(_SDK_PREFIX)


def stripSdkPrefix(model: str) -> str:
    """Remove the ``claude_agent_sdk/`` routing prefix to get the bare model ID."""
    return model[len(_SDK_PREFIX) :] if isClaudeAgentSdkModel(model) else model


def _findClaudeCli() -> str | None:
    """Return the path to the ``claude`` CLI binary, or None if not found."""
    return shutil.which("claude")


def checkClaudeAgentSdkAuth() -> tuple[bool, str]:
    """Check whether the Claude CLI and authentication are ready.

    The CLI authenticates via ``ANTHROPIC_API_KEY`` or the OAuth token
    cached by ``claude setup-token`` (``CLAUDE_CODE_OAUTH_TOKEN``).

    Returns a ``(ready, reason)`` tuple matching the convention used by
    :func:`copilot_auth.checkLlmAuth`.
    """
    if _findClaudeCli() is None:
        return False, "claude_cli_not_found"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return True, ""
    return False, "claude_agent_sdk_auth_needed"


async def claudeAgentSdkCompletion(
    system_prompt: str,
    user_message: str,
    model: str,
    temperature: float = 0.2,
) -> str:
    """Run a single LLM completion via the ``claude`` CLI in print mode.

    Spawns ``claude -p`` as a subprocess with ``--tools ""`` (no tool
    use) so it behaves as a pure text completion.  The subprocess is
    run asynchronously via :func:`asyncio.create_subprocess_exec`.

    Returns the assistant's text response as a string.
    """
    cli = _findClaudeCli()
    if cli is None:
        raise FileNotFoundError(
            "The 'claude' CLI is not installed or not on PATH. "
            "Install it from https://claude.ai/download"
        )

    bare_model = stripSdkPrefix(model)

    cmd = [
        cli,
        "-p",
        "--model", bare_model,
        "--tools", "",
        "--system-prompt", system_prompt,
        "--output-format", "text",
        "--no-session-persistence",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=user_message.encode())

    if proc.returncode != 0:
        err_text = stderr.decode(errors="replace").strip()
        raise RuntimeError(
            f"claude CLI exited with code {proc.returncode}: {err_text}"
        )

    return stdout.decode(errors="replace").strip()
