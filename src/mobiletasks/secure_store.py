"""Protected storage for mobile OAuth refresh tokens and optional LLM keys.

Mobile refresh tokens are DPAPI-only. Access tokens are issued on demand and
remain in the calling process memory. LLM keys use DPAPI on Windows and an
explicit mode-600 development fallback on non-Windows systems.
"""

import base64
import binascii
import ctypes
import json
import os
import sys
import tempfile
from ctypes import wintypes


class SecretStoreError(RuntimeError):
    """Raised when protected token storage cannot be used safely."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


_DPAPI_CONFIGURED = False


def _configure_dpapi(crypt32):
    """Declare Win32 signatures so pointers are handled safely on 64-bit Windows."""
    global _DPAPI_CONFIGURED
    if _DPAPI_CONFIGURED:
        return
    blob_ptr = ctypes.POINTER(_DataBlob)
    crypt32.CryptProtectData.argtypes = [
        blob_ptr,
        ctypes.c_wchar_p,
        blob_ptr,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        blob_ptr,
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        blob_ptr,
        ctypes.POINTER(ctypes.c_wchar_p),
        blob_ptr,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        blob_ptr,
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    _DPAPI_CONFIGURED = True


def _crypt32():
    if sys.platform != "win32":
        raise SecretStoreError("Windows DPAPI is only available on Windows")
    try:
        crypt32 = ctypes.windll.crypt32
        _configure_dpapi(crypt32)
        return crypt32
    except AttributeError as exc:
        raise SecretStoreError("Windows DPAPI library is unavailable") from exc


def _protect(data):
    """Protect bytes with the current Windows user profile."""
    crypt32 = _crypt32()
    raw = bytes(data)
    source = ctypes.create_string_buffer(raw)
    source_blob = _DataBlob(
        len(raw), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte))
    )
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
        ctypes.windll.kernel32.LocalFree(
            ctypes.cast(output_blob.pbData, ctypes.c_void_p)
        )


def _unprotect(data):
    """Unprotect bytes with the current Windows user profile."""
    crypt32 = _crypt32()
    raw = bytes(data)
    source = ctypes.create_string_buffer(raw)
    source_blob = _DataBlob(
        len(raw), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte))
    )
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
        if description.value:
            ctypes.windll.kernel32.LocalFree(ctypes.cast(description, ctypes.c_void_p))
        ctypes.windll.kernel32.LocalFree(
            ctypes.cast(output_blob.pbData, ctypes.c_void_p)
        )


def _atomic_write_bytes(path, payload, mode=None):
    """Write a small secret without sharing a fixed temporary filename."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        if mode is not None and os.name != "nt":
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


class ProtectedTokenStore:
    """Read/write a small JSON token envelope protected by Windows DPAPI."""

    def __init__(self, path):
        self.path = path

    def save(self, refresh_token, account_id=""):
        if not refresh_token or not isinstance(refresh_token, str):
            raise SecretStoreError("A non-empty refresh token is required")
        if len(refresh_token) > 32768:
            raise SecretStoreError("Refresh token is unexpectedly large")
        envelope = {
            "version": 1,
            "account_id": str(account_id or ""),
            "refresh_token": refresh_token,
        }
        encrypted = _protect(
            json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        )
        _atomic_write_bytes(self.path, b"AR-DPAPI-1\n" + base64.b64encode(encrypted))

    def load(self, account_id=""):
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, "rb") as handle:
                marker, encoded = handle.read().split(b"\n", 1)
            if marker != b"AR-DPAPI-1":
                raise SecretStoreError("Unrecognized protected token format")
            encrypted = base64.b64decode(encoded, validate=True)
            envelope = json.loads(_unprotect(encrypted).decode("utf-8"))
        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            binascii.Error,
            SecretStoreError,
            ctypes.ArgumentError,
        ) as exc:
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


class ApiKeyStore:
    """Store the optional LLM key outside settings.json.

    Windows uses DPAPI.  The non-Windows development fallback is a separate
    mode-600 file; it is deliberately not presented as encryption.
    """

    def __init__(self, path):
        self.path = path

    def save(self, value):
        if not isinstance(value, str) or len(value) > 4096:
            raise SecretStoreError("LLM API key is invalid")
        if not value:
            self.delete()
            return
        if sys.platform == "win32":
            payload = _protect(
                json.dumps(
                    {"version": 1, "value": value}, separators=(",", ":")
                ).encode("utf-8")
            )
            data = b"AR-DPAPI-KEY-1\n" + base64.b64encode(payload)
            _atomic_write_bytes(self.path, data)
            return
        _atomic_write_bytes(self.path, value.encode("utf-8"), mode=0o600)

    def load(self):
        if not os.path.exists(self.path):
            return ""
        try:
            with open(self.path, "rb") as handle:
                raw = handle.read(8192)
            if sys.platform == "win32":
                marker, encoded = raw.split(b"\n", 1)
                if marker != b"AR-DPAPI-KEY-1":
                    raise SecretStoreError("Unrecognized protected API key format")
                envelope = json.loads(
                    _unprotect(base64.b64decode(encoded, validate=True)).decode("utf-8")
                )
                value = envelope.get("value") if isinstance(envelope, dict) else None
            else:
                value = raw.decode("utf-8")
        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            binascii.Error,
            SecretStoreError,
            ctypes.ArgumentError,
        ) as exc:
            raise SecretStoreError("LLM API key could not be read") from exc
        if not isinstance(value, str) or len(value) > 4096:
            raise SecretStoreError("LLM API key file is invalid")
        return value

    def delete(self):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except OSError as exc:
            raise SecretStoreError("LLM API key could not be removed") from exc
