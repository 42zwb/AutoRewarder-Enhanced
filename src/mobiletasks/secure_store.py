"""Windows DPAPI-backed storage for mobile OAuth refresh tokens.

Only refresh tokens are persisted.  Access tokens are issued on demand and
remain in the calling process memory.  On non-Windows systems, or when DPAPI
is unavailable, this module refuses to write a plaintext fallback.
"""

import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes


class SecretStoreError(RuntimeError):
    """Raised when protected token storage cannot be used safely."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _crypt32():
    if sys.platform != "win32":
        raise SecretStoreError("Windows DPAPI is only available on Windows")
    try:
        return ctypes.windll.crypt32
    except AttributeError as exc:
        raise SecretStoreError("Windows DPAPI library is unavailable") from exc


def _protect(data):
    """Protect bytes with the current Windows user profile."""
    crypt32 = _crypt32()
    raw = bytes(data)
    source = ctypes.create_string_buffer(raw)
    source_blob = _DataBlob(len(raw), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(source_blob),
        "AutoRewarder mobile token",
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    )
    if not ok:
        raise SecretStoreError(f"CryptProtectData failed: {ctypes.get_last_error()}")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def _unprotect(data):
    """Unprotect bytes with the current Windows user profile."""
    crypt32 = _crypt32()
    raw = bytes(data)
    source = ctypes.create_string_buffer(raw)
    source_blob = _DataBlob(len(raw), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = _DataBlob()
    description = ctypes.c_wchar_p()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source_blob),
        ctypes.byref(description),
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    )
    if not ok:
        raise SecretStoreError(f"CryptUnprotectData failed: {ctypes.get_last_error()}")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        if description:
            ctypes.windll.kernel32.LocalFree(description)
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


class ProtectedTokenStore:
    """Read/write a small JSON token envelope protected by Windows DPAPI."""

    def __init__(self, path):
        self.path = path

    def save(self, refresh_token, account_id=""):
        if not refresh_token or not isinstance(refresh_token, str):
            raise SecretStoreError("A non-empty refresh token is required")
        envelope = {
            "version": 1,
            "account_id": str(account_id or ""),
            "refresh_token": refresh_token,
        }
        encrypted = _protect(json.dumps(envelope, separators=(",", ":")).encode("utf-8"))
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temp_path = self.path + ".tmp"
        with open(temp_path, "wb") as handle:
            handle.write(b"AR-DPAPI-1\n")
            handle.write(base64.b64encode(encrypted))
        os.replace(temp_path, self.path)

    def load(self, account_id=""):
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, "rb") as handle:
                marker, encoded = handle.read().split(b"\n", 1)
            if marker != b"AR-DPAPI-1":
                raise SecretStoreError("Unrecognized protected token format")
            envelope = json.loads(_unprotect(base64.b64decode(encoded)).decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise SecretStoreError("Protected token could not be read") from exc
        if not isinstance(envelope, dict) or not envelope.get("refresh_token"):
            raise SecretStoreError("Protected token envelope is invalid")
        stored_account = str(envelope.get("account_id") or "")
        if account_id and stored_account and stored_account != str(account_id):
            raise SecretStoreError("Protected token belongs to a different account")
        return str(envelope["refresh_token"])

    def delete(self):
        if os.path.exists(self.path):
            os.remove(self.path)
