"""Jarvis -- a menu-bar voice assistant for macOS.

A small icon sits in your menu bar. Click it to start/stop listening, set your
free Groq API key, see the latest exchange, and quit. No terminal needed.

The engine runs on a background thread; this UI polls its state on the main
thread every half second (the safe way to touch AppKit from rumps).
"""
import rumps

import config
from engine import Engine

# Menu-bar glyph per engine state.
_ICONS = {
    "stopped": "⚪️", "stopping": "⚪️", "microphone unavailable": "🚫",
    "waiting for mic…": "🟠", "starting…": "🟠",
    "listening": "🎙️", "listening to you…": "👂", "listening to you": "👂",
    "thinking…": "💭", "speaking…": "🔴", "reminder": "🔔",
}


class JarvisApp(rumps.App):
    def __init__(self):
        super().__init__("Jarvis", title="⚪️", quit_button=None)
        self.engine = Engine()
        self._prompted_for_key = False

        self.status_item = rumps.MenuItem("Status: stopped")
        self.last_item = rumps.MenuItem("Say “Hey Jarvis” to begin")
        self.toggle_item = rumps.MenuItem("Start Listening", callback=self.toggle)
        self.menu = [
            self.status_item,
            self.last_item,
            None,
            self.toggle_item,
            rumps.MenuItem("Set Groq API Key…", callback=self.set_key),
            None,
            rumps.MenuItem("About Jarvis", callback=self.about),
            rumps.MenuItem("Quit Jarvis", callback=self.quit_app),
        ]

        # Auto-start if a key is already saved; otherwise prompt on first tick.
        if config.GROQ_API_KEY:
            self.engine.start()

        self._poll = rumps.Timer(self._tick, 0.5)
        self._poll.start()

    # -- main-thread UI refresh --
    def _tick(self, _timer):
        running = self.engine.running
        state = self.engine.state if running else "stopped"
        self.title = _ICONS.get(state, "🎙️" if running else "⚪️")
        self.status_item.title = f"Status: {state}"
        self.toggle_item.title = "Stop Listening" if running else "Start Listening"
        lt = self.engine.last_transcript
        if lt:
            text = lt[1] if len(lt[1]) <= 70 else lt[1][:69] + "…"
            self.last_item.title = f"{lt[0]}: {text}"
        if not config.GROQ_API_KEY and not self._prompted_for_key:
            self._prompted_for_key = True
            self.set_key(None)

    # -- menu actions --
    def toggle(self, _):
        if self.engine.running:
            self.engine.stop()
        elif not config.GROQ_API_KEY:
            self.set_key(None)
        else:
            self.engine.start()

    def set_key(self, _):
        win = rumps.Window(
            title="Groq API Key",
            message="Paste your free Groq API key (from console.groq.com/keys).\n"
                    "Jarvis uses it for speech recognition and its brain.",
            default_text=config.GROQ_API_KEY or "",
            ok="Save", cancel="Cancel", dimensions=(360, 24),
        )
        resp = win.run()
        if resp.clicked:
            key = (resp.text or "").strip()
            config.save_setting("GROQ_API_KEY", key)
            if key:
                if self.engine.running:
                    self.engine.stop()
                self.engine.start()
                rumps.notification("Jarvis", "API key saved", "Starting up…")

    def about(self, _):
        rumps.alert(
            title="Jarvis",
            message="A hands-free voice assistant.\n\n"
                    "Say “Hey Jarvis”, then ask a question, or set a reminder "
                    "like “remind me to call mom tomorrow at 8pm”.\n\n"
                    "Settings are stored in:\n~/Library/Application Support/Jarvis/",
            ok="OK",
        )

    def quit_app(self, _):
        try:
            self.engine.stop()
        except Exception:
            pass
        rumps.quit_application()


def main():
    JarvisApp().run()


if __name__ == "__main__":
    main()
