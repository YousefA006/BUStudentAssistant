"""Configuration, loaded from the .env file next to this script."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")

# ---- AI provider: "gemini", "groq" or "anthropic" (Claude) ----
_PROVIDERS = {
    #            base URL (OpenAI-compatible chat API)                  answer model               query-rewrite model
    "gemini":    ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-flash-latest", "gemini-flash-latest"),
    "groq":      ("https://api.groq.com/openai/v1",                     "openai/gpt-oss-120b",     "openai/gpt-oss-20b"),
    "anthropic": ("https://api.anthropic.com/v1",                       "claude-sonnet-5-5",       "claude-haiku-5-5"),
    "openai":    ("https://api.openai.com/v1",                          "gpt-4o-mini",             "gpt-4o-mini"),
}
# If a model above gets retired, the app picks the first of these that the provider still offers.
PREFERRED_MODELS = {
    "groq": ["openai/gpt-oss-120b", "qwen/qwen3.6-27b", "openai/gpt-oss-20b"],
    "gemini": ["gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest"],
}
_KEY_VARS = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}

_KEY_PREFIXES = (("gsk_", "groq"), ("AIza", "gemini"), ("sk-ant-", "anthropic"), ("sk-", "openai"))


def _provider_from_key(key: str):
    return next((p for prefix, p in _KEY_PREFIXES if key.startswith(prefix)), None)


API_KEY = (os.environ.get("API_KEY") or "").strip().strip('"').strip("'")
if API_KEY in ("your-key-here", ""):
    API_KEY = ""
PROVIDER = (os.environ.get("PROVIDER") or "").strip().lower()
if not API_KEY:  # provider-specific variable names also work, e.g. GROQ_API_KEY=...
    for p, var in _KEY_VARS.items():
        if (os.environ.get(var) or "").strip() and (not PROVIDER or PROVIDER == p):
            API_KEY, PROVIDER = os.environ[var].strip(), PROVIDER or p
            break

# The key itself tells us the provider (gsk_ = Groq, AIza = Gemini, sk-ant- = Claude). It wins over a
# PROVIDER line that doesn't match it, so a forgotten PROVIDER=... in .env can't break the app.
_detected = _provider_from_key(API_KEY)
if _detected and PROVIDER != _detected and not (PROVIDER == "openai" and os.environ.get("API_BASE")):
    if PROVIDER:
        print(f"[config] PROVIDER={PROVIDER} doesn't match your API key; using {_detected} (detected from the key).")
    PROVIDER = _detected
PROVIDER = PROVIDER or "groq"
if PROVIDER not in _PROVIDERS:
    raise SystemExit(f"Unknown PROVIDER '{PROVIDER}' in .env. Use one of: {', '.join(_PROVIDERS)}")

API_BASE = (os.environ.get("API_BASE") or _PROVIDERS[PROVIDER][0]).rstrip("/")
ANSWER_MODEL = os.environ.get("ANSWER_MODEL") or _PROVIDERS[PROVIDER][1]
QUERY_MODEL = os.environ.get("QUERY_MODEL") or _PROVIDERS[PROVIDER][2]

# Shared knowledge base: every PDF in this folder (and its subfolders) is indexed for all students.
def _dir(name: str, default: str) -> Path:
    p = Path(os.environ.get(name) or default)
    return (p if p.is_absolute() else BASE_DIR / p).resolve()


DATA_DIR = _dir("DATA_DIR", "data")
# App storage: database + PDFs uploaded through the website.
STORAGE_DIR = _dir("STORAGE_DIR", "storage")
UPLOAD_DIR = STORAGE_DIR / "uploads"
DB_PATH = STORAGE_DIR / "app.db"

TOP_K = int(os.environ.get("TOP_K") or "6")
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB") or "25")
HOST = os.environ.get("HOST") or "127.0.0.1"
PORT = int(os.environ.get("PORT") or "5000")

for d in (DATA_DIR, STORAGE_DIR, UPLOAD_DIR):
    d.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    key_file = STORAGE_DIR / "secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    SECRET_KEY = key_file.read_text(encoding="utf-8").strip()
