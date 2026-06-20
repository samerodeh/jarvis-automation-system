"""Settings for the Jarvis app.

Values are read in priority order from: real environment variables, then a user
config file at ``~/Library/Application Support/Jarvis/config.json`` (written by
the app's Settings menu), then sensible defaults. That JSON file is where your
Groq API key and preferences live -- no terminal or .env editing required.
"""
import json
import os
from pathlib import Path


def app_support_dir() -> Path:
    """Writable per-user folder for settings, reminders, logs (created if needed)."""
    d = Path.home() / "Library" / "Application Support" / "Jarvis"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = app_support_dir() / "config.json"


def load_settings() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def save_setting(key: str, value) -> None:
    """Persist one setting and apply it to the running app immediately."""
    data = load_settings()
    data[key] = value
    try:
        CONFIG_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass
    os.environ[key] = "" if value is None else str(value)
    refresh()


def _dev_dotenv() -> None:
    """Load a local .env when running from source (developer convenience only)."""
    p = Path(__file__).resolve().parent / ".env"
    if not p.exists():
        return
    import re
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = re.split(r"\s+#", v, maxsplit=1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


# Seed the environment from .env (dev) and the saved config file (real env wins).
_dev_dotenv()
for _k, _v in load_settings().items():
    if _v is not None:
        os.environ.setdefault(_k, str(_v))


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _read() -> None:
    """(Re)read every setting from the environment into module globals. The app
    calls refresh() after a settings change so a freshly started engine sees it."""
    g = globals()
    # The app is cloud-only: Groq powers both the brain and speech-to-text.
    g["LLM_PROVIDER"] = "groq"
    g["STT_PROVIDER"] = "groq"
    g["GROQ_API_KEY"] = os.environ.get("GROQ_API_KEY", "").strip()
    g["GROQ_MODEL"] = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    g["GROQ_STT_MODEL"] = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo").strip()
    g["STT_PROMPT"] = os.environ.get("STT_PROMPT", "").strip()
    g["SAMPLE_RATE"] = 16000
    g["RECORD_SECONDS"] = float(os.environ.get("RECORD_SECONDS", "4"))

    # Wake word + voice-activity detection
    g["WAKE_WORD"] = os.environ.get("WAKE_WORD", "jarvis").strip().lower()
    g["END_SILENCE_SEC"] = float(os.environ.get("END_SILENCE_SEC", "1.5"))
    g["MAX_UTTERANCE_SEC"] = float(os.environ.get("MAX_UTTERANCE_SEC", "30"))
    g["COMMAND_TIMEOUT_SEC"] = float(os.environ.get("COMMAND_TIMEOUT_SEC", "5"))
    g["VAD_SENSITIVITY"] = float(os.environ.get("VAD_SENSITIVITY", "3.0"))
    g["USE_OPENWAKEWORD"] = _flag("USE_OPENWAKEWORD", "true")
    g["WAKE_MODEL"] = os.environ.get("WAKE_MODEL", "hey_jarvis").strip()
    g["WAKE_THRESHOLD"] = float(os.environ.get("WAKE_THRESHOLD", "0.5"))
    g["WAKE_VAD_THRESHOLD"] = float(os.environ.get("WAKE_VAD_THRESHOLD", "0.5"))
    g["WAKE_MIN_PEAK"] = float(os.environ.get("WAKE_MIN_PEAK", "0.04"))

    # Text to speech (macOS `say`)
    g["TTS_VOICE"] = os.environ.get("TTS_VOICE", "Daniel").strip()
    g["TTS_RATE"] = int(os.environ.get("TTS_RATE", "190"))

    # Live tools
    g["DEFAULT_CITY"] = os.environ.get("DEFAULT_CITY", "").strip()
    g["WEATHER_UNITS"] = os.environ.get("WEATHER_UNITS", "celsius").strip()

    # Persona
    g["ASSISTANT_NAME"] = os.environ.get("ASSISTANT_NAME", "Jarvis").strip()

    # Transcript colors (only matter if run from a terminal; the app uses the UI)
    g["USE_COLOR"] = _flag("USE_COLOR", "false")
    g["USER_COLOR"] = os.environ.get("USER_COLOR", "white").strip().lower()
    g["ASSISTANT_COLOR"] = os.environ.get("ASSISTANT_COLOR", "red").strip().lower()

    # Reminders
    g["REMINDER_INTERVAL_MIN"] = int(os.environ.get("REMINDER_INTERVAL_MIN", "5"))
    g["REMINDER_WAKE_START"] = int(os.environ.get("REMINDER_WAKE_START", "8"))
    g["REMINDER_WAKE_END"] = int(os.environ.get("REMINDER_WAKE_END", "22"))
    g["REMINDER_CHECK_SEC"] = int(os.environ.get("REMINDER_CHECK_SEC", "30"))
    g["ADD_TO_MAC_REMINDERS"] = _flag("ADD_TO_MAC_REMINDERS", "true")


def refresh() -> None:
    _read()


_read()
