"""The Jarvis voice engine: wake-word loop, transcription, brain, and reminders.

Runs on a background thread so a GUI (the menu-bar app) can drive it with
start()/stop(). It exposes ``state`` and ``last_transcript`` attributes that the
UI polls on the main thread -- no cross-thread UI calls, no terminal.
"""
import re
import threading
import time

import config
import audio
import reminders
from brain import Brain

_WAKE_RE = re.compile(r"\b(?:hey\s+)?(jarvis|jarvus|jervis|jarviss|jarvi)\b", re.I)
_ACK_WORDS = ("done", "got it", "i did it", "i've done it", "i did", "finished",
              "complete", "completed", "handled", "taken care", "all done",
              "acknowledge", "dismiss", "stop reminding")


def _strip_wake(text):
    out = _WAKE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", out).strip(" ,.:;!?-").strip()


def _is_ack(text):
    t = _strip_wake(text).lower().strip(" .!?,")
    return any(w in t for w in _ACK_WORDS)


class Engine:
    """Background voice loop. Read ``state`` / ``last_transcript`` from the UI."""

    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self.state = "stopped"          # short status string for the UI
        self.last_transcript = None     # (speaker_label, text) or None
        self.last_error = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="jarvis-engine", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.state = "stopping"

    # -- observable updates --
    def _set(self, state):
        self.state = state

    def _emit(self, speaker, text):
        label = {"you": "You", "jarvis": config.ASSISTANT_NAME, "system": "Note"}.get(speaker, speaker)
        self.last_transcript = (label, text)

    # -- mic with self-healing (the device can appear late at login) --
    def _open_listener(self):
        from listener import Listener
        for _ in range(30):
            if self._stop.is_set():
                return None
            try:
                return Listener().start()
            except Exception as exc:
                self.last_error = str(exc)
                self._set("waiting for mic…")
                try:
                    import sounddevice as sd
                    sd._terminate(); sd._initialize()  # refresh device list
                except Exception:
                    pass
                self._stop.wait(5)
        return None

    def _run(self):
        self._set("starting…")
        config.refresh()
        audio.prepare()
        brain = Brain()
        if not brain.ready:
            self._emit("system", brain.error)

        listener = self._open_listener()
        if listener is None:
            self._set("microphone unavailable")
            return

        detector = None
        if config.USE_OPENWAKEWORD:
            try:
                from wakeword import WakeWord
                detector = WakeWord()
            except Exception as exc:
                self._emit("system", f"wake word unavailable ({exc})")

        try:
            audio.speak(f"{config.ASSISTANT_NAME} online.")
            listener.flush()
            self._set("listening")
            while not self._stop.is_set():
                if detector is not None:
                    woke = listener.wait_for_wake(detector, timeout_sec=config.REMINDER_CHECK_SEC)
                    if self._stop.is_set():
                        break
                    if not woke:
                        if self._announce_due(listener):
                            detector.reset()
                        continue
                    audio.chime()
                    time.sleep(0.4)
                    listener.flush()
                    self._set("listening to you…")
                    command = audio.transcribe(
                        listener.listen_utterance(start_timeout_sec=config.COMMAND_TIMEOUT_SEC))
                    detector.reset()
                else:
                    command = self._transcription_wake(listener)

                if self._stop.is_set():
                    break
                if not command:
                    self._set("listening")
                    continue

                self._emit("you", command)
                self._set("thinking…")
                reply = brain.ask(command)
                if reply:
                    self._emit("jarvis", reply)
                    self._set("speaking…")
                    audio.speak(reply)
                time.sleep(0.3)
                listener.flush()
                self._set("listening")
        finally:
            try:
                listener.stop()
            except Exception:
                pass
            self._set("stopped")

    def _transcription_wake(self, listener):
        """Fallback when openWakeWord is unavailable: transcribe and match the wake word."""
        while not self._stop.is_set():
            clip = listener.listen_utterance(start_timeout_sec=config.REMINDER_CHECK_SEC)
            if clip.size < int(0.25 * config.SAMPLE_RATE):
                self._announce_due(listener)
                continue
            text = audio.transcribe(clip)
            if text and _WAKE_RE.search(text):
                return _strip_wake(text)
        return None

    def _announce_due(self, listener):
        """Speak one due reminder, listen briefly for 'done'. Returns True if one
        was announced (so the caller can reset the wake detector)."""
        due = reminders.due_to_announce()
        if not due:
            return False
        r = due[0]
        reminders.mark_announced(r["id"])
        self._emit("jarvis", f"Reminder: {r['text']}")
        self._set("reminder")
        audio.speak(f"Reminder, sir: {r['text']}. Say done when you've taken care of it.")
        time.sleep(0.3)
        listener.flush()
        reply = audio.transcribe(listener.listen_utterance(start_timeout_sec=6))
        if reply and _is_ack(reply):
            reminders.acknowledge(r["id"])
            self._emit("you", reply)
            audio.speak("Done, sir. I won't remind you about that again.")
        listener.flush()
        self._set("listening")
        return True
