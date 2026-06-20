#!/bin/bash
# Build and ad-hoc code-sign Jarvis.app, with the microphone entitlement so macOS
# will actually prompt for (and grant) mic access -- the thing that fails for
# unsigned bundles. Run inside the build venv (see README).
set -e
cd "$(dirname "$0")"

echo "==> Cleaning previous build"
rm -rf build dist

echo "==> Building Jarvis.app with py2app"
python setup.py py2app

APP="dist/Jarvis.app"

echo "==> Bundling PortAudio (py2app skips sounddevice's sibling data dir)"
SP="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
if [ -d "$SP/_sounddevice_data" ]; then
  cp -R "$SP/_sounddevice_data" "$APP/Contents/Resources/lib/python3.12/"
  echo "   added libportaudio.dylib"
fi

echo "==> Ad-hoc code-signing with entitlements"
# Sign nested code first, then the app, with the mic/automation entitlement.
codesign --force --deep --options runtime \
  --entitlements entitlements.plist \
  --sign - "$APP"

echo "==> Verifying signature"
codesign --verify --verbose=2 "$APP" || true
codesign -d --entitlements - "$APP" 2>/dev/null | grep -i audio-input && \
  echo "   microphone entitlement present ✓" || echo "   (entitlement check inconclusive)"

echo ""
echo "Done -> $APP"
echo "Launch it:  open \"$APP\""
echo "First launch: approve the microphone (and Reminders) prompts once."
