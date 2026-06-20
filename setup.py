"""py2app build script for the Jarvis menu-bar app.

Build a self-contained Jarvis.app:
    ./build.sh          # builds, then ad-hoc code-signs with the mic entitlement

The app is cloud-only (Groq for brain + speech), so we deliberately exclude the
heavy local-ML stack (torch, whisper, tensorflow, …) to keep the bundle small.
The three openWakeWord ONNX models are bundled as data so nothing downloads.
"""
from setuptools import setup

APP = ["app.py"]

DATA_FILES = [
    ("models", [
        "assets/models/hey_jarvis_v0.1.onnx",
        "assets/models/melspectrogram.onnx",
        "assets/models/embedding_model.onnx",
    ]),
]

OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "Jarvis",
        "CFBundleDisplayName": "Jarvis",
        "CFBundleIdentifier": "com.samer.jarvis",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSUIElement": True,  # menu-bar app: no Dock icon, no main window
        "LSMinimumSystemVersion": "12.0",
        "NSMicrophoneUsageDescription":
            "Jarvis listens for “Hey Jarvis” and your spoken commands.",
        "NSAppleEventsUsageDescription":
            "Jarvis can add your reminders to the macOS Reminders app.",
    },
    "packages": [
        "rumps", "openwakeword", "onnxruntime", "sounddevice", "numpy",
        "requests", "certifi", "charset_normalizer", "idna", "urllib3",
        "cffi", "ddgs",
    ],
    "includes": [
        "config", "audio", "brain", "tools", "reminders", "listener",
        "wakeword", "engine", "_cffi_backend",
    ],
    "excludes": [
        "torch", "torchaudio", "whisper", "openai_whisper", "tensorflow",
        "tflite_runtime", "matplotlib", "pandas", "tkinter", "PyQt5", "PyQt6",
        "PySide6", "IPython", "notebook", "pytest", "test", "tests",
    ],
}

setup(
    app=APP,
    name="Jarvis",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
