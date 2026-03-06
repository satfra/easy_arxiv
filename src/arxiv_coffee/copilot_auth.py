from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path


def isCopilotModel(model: str) -> bool:
    """Check whether the model string uses the github_copilot/ provider."""
    return model.startswith("github_copilot/")


def _tokenDir() -> Path:
    """Return the directory where Copilot tokens are stored."""
    return Path(
        os.environ.get(
            "GITHUB_COPILOT_TOKEN_DIR",
            Path.home() / ".config" / "litellm" / "github_copilot",
        )
    )


def _accessTokenPath() -> Path:
    """Return the path to the cached OAuth access token file."""
    filename = os.environ.get("GITHUB_COPILOT_ACCESS_TOKEN_FILE", "access-token")
    return _tokenDir() / filename


def _apiKeyPath() -> Path:
    """Return the path to the cached short-lived API key JSON."""
    filename = os.environ.get("GITHUB_COPILOT_API_KEY_FILE", "api-key.json")
    return _tokenDir() / filename


def needsCopilotAuth() -> bool:
    """Check whether GitHub Copilot OAuth login is required.

    Returns True if there is no cached access token on disk. If a token
    file exists (even if the short-lived API key is expired), litellm can
    refresh it silently — so we only trigger the device flow when the
    long-lived access token is completely absent.
    """
    path = _accessTokenPath()
    if not path.exists():
        return True
    try:
        content = path.read_text(encoding="utf-8").strip()
        return not content
    except OSError:
        return True


def hasValidApiKey() -> bool:
    """Check whether a valid (non-expired) Copilot API key is cached."""
    path = _apiKeyPath()
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("expires_at", 0) > datetime.now().timestamp()
    except (OSError, json.JSONDecodeError, KeyError):
        return False


def getDeviceCode() -> dict[str, str]:
    """Request a new device code from GitHub for OAuth device flow.

    Returns a dict with keys: device_code, user_code, verification_uri.
    This is a synchronous HTTP call — wrap in asyncio.to_thread() from
    async code.
    """
    from litellm.llms.github_copilot.authenticator import Authenticator

    auth = Authenticator()
    return auth._get_device_code()


def pollForAccessToken(device_code: str) -> str:
    """Poll GitHub until the user authorises the device code.

    This blocks for up to ~60 seconds (12 attempts x 5 s). Returns the
    OAuth access token on success. Wrap in asyncio.to_thread() from
    async code.
    """
    from litellm.llms.github_copilot.authenticator import Authenticator

    auth = Authenticator()
    access_token = auth._poll_for_access_token(device_code)

    # Persist the token so litellm can use it on subsequent calls
    path = _accessTokenPath()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(access_token, encoding="utf-8")

    return access_token


def checkLlmAuth(model: str, api_key: str) -> tuple[bool, str]:
    """Check whether LLM authentication is ready.

    Returns a (ready, reason) tuple.  ``ready`` is True when the caller
    can proceed with LLM calls.  When False, ``reason`` explains what is
    missing:

    - ``"copilot_auth_needed"`` — a Copilot model is configured but no
      cached token exists; the caller should trigger the device flow.
    - ``"no_api_key"`` — a non-Copilot model is configured but the API
      key is empty.
    """
    if isCopilotModel(model):
        if needsCopilotAuth():
            return False, "copilot_auth_needed"
        return True, ""

    if not api_key:
        return False, "no_api_key"
    return True, ""


async def runDeviceFlow() -> tuple[str, str, asyncio.Task[str]]:
    """Start the GitHub Copilot OAuth device flow.

    Returns (user_code, verification_uri, poll_task) where poll_task is
    an asyncio Task that resolves to the access token once the user
    authorises in the browser.
    """
    info = await asyncio.to_thread(getDeviceCode)
    user_code: str = info["user_code"]
    verification_uri: str = info["verification_uri"]
    device_code: str = info["device_code"]

    poll_task = asyncio.create_task(asyncio.to_thread(pollForAccessToken, device_code))
    return user_code, verification_uri, poll_task
