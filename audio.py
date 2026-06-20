"""Audio I/O -- microphone capture, speech-to-text (Groq Whisper), speech (macOS say).

This app is cloud-only: transcription goes to Groq's hosted Whisper-large, so
there's no local Whisper/torch to bundle. Heavy imports (sounddevice, numpy) are
lazy so importing this module never requires a microphone.
"""
import subprocess

import config


def record(seconds: float | None = None):
    """Record from the default microphone and return a mono float32 array."""
    import numpy as np  # noqa: F401  (sounddevice needs numpy available)
    import sounddevice as sd

    seconds = seconds or config.RECORD_SECONDS
    audio = sd.rec(
        int(seconds * config.SAMPLE_RATE),
        samplerate=config.SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return audio.flatten()


def prepare() -> None:
    """Nothing to warm up -- Groq STT is remote."""
    return


# Stock phrases Whisper invents from silence / non-speech audio.
_HALLUCINATIONS = {
    "", ".", "you", "thank you", "thanks", "thank you very much",
    "thanks for watching", "thank you for watching", "thanks for watching!",
    "please subscribe", "bye", "goodbye", "okay", "ok", "so", "uh", "um",
    "hmm", "you're welcome", "i'm sorry", "subtitles by the amara.org community",
}


def _looks_like_speech(audio) -> bool:
    """Conservative gate: reject near-silent clips so the transcriber can't
    invent phantom phrases. Real speech (peak ~0.15) passes easily."""
    import numpy as np
    if audio.size < int(0.3 * config.SAMPLE_RATE):
        return False
    return float(np.max(np.abs(audio))) >= 0.02


def _is_hallucination(text) -> bool:
    """True for the stock phrases Whisper emits on silence/non-speech audio."""
    t = text.strip().lower().strip(" .!?,\"'")
    return t in _HALLUCINATIONS or len(t) <= 1


def transcribe(audio) -> str:
    """Turn a recorded clip into text via Groq's hosted Whisper-large. Returns ''
    for non-speech (silence, echo, faint noise) or when STT is unavailable."""
    if not _looks_like_speech(audio):
        return ""
    if not config.GROQ_API_KEY:
        return ""
    text = _transcribe_groq(audio)
    if text is None:
        return ""
    return "" if _is_hallucination(text) else text


def _groq_stt_params():
    params = {"model": config.GROQ_STT_MODEL, "language": "en",
              "response_format": "json", "temperature": "0"}
    if config.STT_PROMPT:  # optional; off by default since priming can echo
        params["prompt"] = config.STT_PROMPT
    return params


def _transcribe_groq(audio):
    """Send the clip to Groq's hosted Whisper-large. Returns text, or None on failure."""
    import io
    import wave

    import numpy as np
    import requests

    buf = io.BytesIO()
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(config.SAMPLE_RATE)
        wav.writeframes(pcm)
    buf.seek(0)
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
            files={"file": ("speech.wav", buf, "audio/wav")},
            data=_groq_stt_params(),
            timeout=30,
        )
    except Exception as exc:
        print(f"  [stt] Groq request failed ({exc}).")
        return None
    if resp.status_code != 200:
        print(f"  [stt] Groq STT error {resp.status_code}: {resp.text[:140]}")
        return None
    return resp.json().get("text", "").strip()


def speak(text: str) -> None:
    """Speak text aloud via the macOS ``say`` command (free, built-in).

    Falls back to the system default voice if the configured one isn't
    installed, and stays silent (rather than crashing) on non-macOS systems.
    """
    if not text:
        return
    base = ["say", "-r", str(config.TTS_RATE)]
    try:
        if config.TTS_VOICE:
            result = subprocess.run(base + ["-v", config.TTS_VOICE, text])
            if result.returncode == 0:
                return
        subprocess.run(base + [text])
    except FileNotFoundError:
        pass  # `say` only exists on macOS


def chime() -> None:
    """Play a short, non-blocking 'I'm listening' cue (macOS system sound)."""
    try:
        subprocess.Popen(
            ["afplay", "/System/Library/Sounds/Tink.aiff"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass
