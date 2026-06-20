# Jarvis — a menu-bar voice assistant for macOS

A hands-free voice assistant that lives in your menu bar. Say **“Hey Jarvis”**,
then ask a question, check the weather, search the web, or set a reminder. No
terminal required — it’s a normal macOS app you double-click.

- 🎙️ **Menu-bar icon** — click to Start/Stop, set your API key, quit.
- 🗣️ **Wake word** “Hey Jarvis” (local, offline detection — no audio leaves your Mac until you speak a command).
- 🧠 **Brain + speech** powered by [Groq](https://console.groq.com/keys) (free API key).
- ⏰ **Reminders** — “remind me to call mom tomorrow at 8pm”; it nags you out loud until you say *done*, and adds the reminder to the macOS Reminders app (→ iPhone via iCloud).
- 🌤️ Live **weather**, **web search**, and **clock**.

## Install (for end users)

1. Double-click **`Jarvis.app`**.
2. On first launch, **approve the Microphone prompt** (and the Reminders prompt the first time you set a reminder).
3. Paste your free **Groq API key** when asked (get one at <https://console.groq.com/keys>).
4. Say **“Hey Jarvis”** — the icon changes while it listens and replies.

Settings and reminders are stored in `~/Library/Application Support/Jarvis/`.

> **Note on sharing:** the build is *ad-hoc signed*, which is enough for the
> microphone prompt to work. macOS Gatekeeper will still flag an app from an
> unidentified developer — on another Mac, right-click the app → **Open** the
> first time (or run `xattr -dr com.apple.quarantine Jarvis.app`). For
> friction-free distribution you’d notarize it with an Apple Developer ID (see
> below).

## Build it yourself

Requires Python 3.12 (the framework build, for a proper `.app`).

```bash
cd ~/projects/jarvis
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./build.sh            # -> dist/Jarvis.app  (built + ad-hoc signed)
open dist/Jarvis.app
```

To run from source without building (developer mode):

```bash
source .venv/bin/activate
python app.py
```

## Project layout

| File | Role |
|---|---|
| `app.py` | Menu-bar app (rumps): icon, menu, settings, polls the engine. **Entry point.** |
| `engine.py` | Background voice loop: wake word → transcribe → brain → speak; reminder nagging. |
| `config.py` | Settings, loaded from `Application Support/Jarvis/config.json` (set via the menu). |
| `audio.py` | Mic capture, Groq speech-to-text, macOS `say` text-to-speech. |
| `brain.py` | Groq LLM with tool-calling (weather, search, clock, reminders). |
| `tools.py` | The live tools. |
| `reminders.py` | Local reminder store + nag scheduler + macOS Reminders sync. |
| `listener.py` | Mic stream + energy VAD (captures one utterance at a time). |
| `wakeword.py` | openWakeWord “Hey Jarvis” detector (bundled ONNX models). |
| `setup.py` / `entitlements.plist` / `build.sh` | py2app packaging + mic entitlement + signing. |
| `assets/models/` | Bundled wake-word ONNX models. |

## Optional: notarize for friction-free sharing

With a paid Apple Developer account:

```bash
# Sign with your Developer ID instead of ad-hoc:
codesign --force --deep --options runtime --entitlements entitlements.plist \
  --sign "Developer ID Application: YOUR NAME (TEAMID)" dist/Jarvis.app
# Zip + notarize:
ditto -c -k --keepParent dist/Jarvis.app Jarvis.zip
xcrun notarytool submit Jarvis.zip --apple-id you@example.com --team-id TEAMID --wait
xcrun stapler staple dist/Jarvis.app
```

Then anyone can open it with no Gatekeeper warning.
