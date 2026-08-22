"""Small security helpers shared by the GUI, browser and persistence layers."""

import re
import json
import os
import tempfile
from urllib.parse import urlparse

_BEARER_RE = re.compile(r"(?i)(\bBearer\s+)[^\s,;]+")
_SECRET_RE = re.compile(
    r"(?i)(\b(?:access[_ -]?token|refresh[_ -]?token|api[_ -]?key|authorization)\b\s*[:=]\s*)([^\s,;]+)"
)


def safe_log_text(value, limit=2000):
    """Return bounded, single-line text with common credentials redacted."""
    text = str(value or "")
    text = "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in text)
    text = _BEARER_RE.sub(r"\1<redacted>", text)
    text = _SECRET_RE.sub(r"\1<redacted>", text)
    return text[: max(80, int(limit))]


def is_allowed_https_url(value, allowed_suffixes):
    """Allow only HTTPS URLs whose hostname is an exact/suffix match."""
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return False
    # Never smuggle credentials into a browser URL supplied by a page.
    if parsed.username is not None or parsed.password is not None:
        return False
    host = parsed.hostname.lower().rstrip(".")
    for suffix in allowed_suffixes:
        suffix = str(suffix).lower().rstrip(".")
        if host == suffix or host.endswith("." + suffix):
            return True
    return False


def is_safe_rewards_url(value):
    """Validate URLs that the Rewards dashboard may legitimately open."""
    return is_allowed_https_url(value, ("bing.com", "microsoft.com", "msn.com"))


def atomic_write_json(path, data, indent=4):
    """Atomically write JSON using a unique same-directory temp file."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=indent, ensure_ascii=False)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(temp_path, path)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
