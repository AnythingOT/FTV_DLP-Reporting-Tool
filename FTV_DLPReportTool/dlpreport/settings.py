"""Settings in %APPDATA%\\DLPReport\\settings.json. Tokens and passwords are encrypted with
Windows DPAPI (readable only by the same Windows user on the same PC)."""

import base64
import json
import logging
import os
import sys

log = logging.getLogger("dlpreport")

SECRET_KEYS = ("token", "password")

DEFAULT_GENERAL = {
    "output_folder": os.path.join(os.path.expanduser("~"), "Documents", "DLP Reports"),
    "max_days": 1,
    "max_tags": 100,
    # advanced
    "batch_size": 25,
    "timeout_s": 120,
    "value_alert": 2_000_000,
    "gap_tolerance": 2.5,
}


def new_profile(name="Local HMI PC", host="localhost"):
    return {"name": name, "host": host, "port": 8086, "https": False, "verify_ssl": False,
            "org": "Rockwell", "auth": "token", "token": "", "username": "", "password": "",
            "tz": "local", "heartbeat_tag": "", "last_tags": [], "last_bucket": "", "groups": {}}


def settings_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "DLPReport")
    os.makedirs(path, exist_ok=True)
    return path


def settings_path():
    return os.path.join(settings_dir(), "settings.json")


def log_path():
    return os.path.join(settings_dir(), "dlp_report.log")


def _dpapi(data, encrypt):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = Blob()
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(blob_in), None, None, None, None, 1, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


def encrypt_secret(text):
    if not text:
        return ""
    if sys.platform == "win32":
        return "dpapi:" + base64.b64encode(_dpapi(text.encode("utf-8"), True)).decode()
    return "plain:" + base64.b64encode(text.encode("utf-8")).decode()


def decrypt_secret(stored):
    if not stored:
        return ""
    kind, _, payload = stored.partition(":")
    raw = base64.b64decode(payload)
    if kind == "dpapi":
        return _dpapi(raw, False).decode("utf-8")
    return raw.decode("utf-8")


def load_settings():
    data = {}
    try:
        with open(settings_path(), encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        pass
    except Exception:
        log.exception("Could not read settings; using defaults")
    general = {**DEFAULT_GENERAL, **{k: v for k, v in data.get("general", {}).items() if k in DEFAULT_GENERAL}}
    profiles = []
    for stored in data.get("profiles", []):
        prof = {**new_profile(), **{k: v for k, v in stored.items() if not k.endswith("_enc")}}
        for key in SECRET_KEYS:
            try:
                prof[key] = decrypt_secret(stored.get(f"{key}_enc", ""))
            except Exception:
                log.exception("Could not decrypt %s for %s", key, prof.get("name"))
                prof[key] = ""
        profiles.append(prof)
    return {"general": general, "profiles": profiles, "last_profile": data.get("last_profile", "")}


def save_settings(settings):
    out = {"general": settings["general"], "last_profile": settings.get("last_profile", ""), "profiles": []}
    for prof in settings["profiles"]:
        stored = {k: v for k, v in prof.items() if k not in SECRET_KEYS}
        for key in SECRET_KEYS:
            stored[f"{key}_enc"] = encrypt_secret(prof.get(key, ""))
        out["profiles"].append(stored)
    tmp = settings_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    os.replace(tmp, settings_path())
