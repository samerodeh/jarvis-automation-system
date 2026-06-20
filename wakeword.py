"""Local wake-word detection with openWakeWord (free, offline, no account).

Listens for "Hey Jarvis" with a tiny pretrained model, so the assistant can
ignore all other sound WITHOUT transcribing it. The three required ONNX models
(wake word, melspectrogram, embedding) are bundled with the app and loaded by
explicit path, so nothing is ever downloaded at runtime.
"""
import collections
import os
import sys
from pathlib import Path

import numpy as np

import config


def _models_dir():
    """Locate the bundled ONNX models, whether running from source or inside the
    packaged .app (where data lands in Contents/Resources)."""
    candidates = []
    here = Path(__file__).resolve().parent
    candidates += [here / "assets" / "models", here / "models"]
    if os.environ.get("RESOURCEPATH"):
        candidates.append(Path(os.environ["RESOURCEPATH"]) / "models")
    exe = Path(sys.executable).resolve()
    candidates.append(exe.parent.parent / "Resources" / "models")  # Contents/MacOS -> Resources
    for c in candidates:
        if (c / "hey_jarvis_v0.1.onnx").exists():
            return c
    return None


class WakeWord:
    def __init__(self):
        from openwakeword.model import Model

        md = _models_dir()
        kwargs = dict(inference_framework="onnx")
        if md is not None:
            kwargs["wakeword_models"] = [str(md / "hey_jarvis_v0.1.onnx")]
            kwargs["melspec_model_path"] = str(md / "melspectrogram.onnx")
            kwargs["embedding_model_path"] = str(md / "embedding_model.onnx")
        else:
            # No bundled models -> fall back to openWakeWord's own (downloads once).
            try:
                import openwakeword
                openwakeword.utils.download_models()
            except Exception:
                pass
            kwargs["wakeword_models"] = [config.WAKE_MODEL]

        if config.WAKE_VAD_THRESHOLD > 0:
            kwargs["vad_threshold"] = config.WAKE_VAD_THRESHOLD

        self.threshold = config.WAKE_THRESHOLD
        self._model = Model(**kwargs)
        self._recent = collections.deque(maxlen=8)  # ~0.6 s of recent peaks
        self.last_score = 0.0

    def reset(self):
        try:
            self._model.reset()
        except Exception:
            pass
        self._recent.clear()

    def detect(self, frame_float32) -> bool:
        """Feed a frame (float32 in [-1, 1]); True if the wake word just fired.

        Guards against openWakeWord spuriously activating on digital silence: a
        hit only counts if there was real audio in the last ~0.6 s."""
        pcm16 = (np.clip(frame_float32, -1.0, 1.0) * 32767).astype(np.int16)
        scores = self._model.predict(pcm16)  # always feed, to keep its buffer continuous
        self.last_score = max(scores.values(), default=0.0)
        self._recent.append(float(np.max(np.abs(frame_float32))))
        if max(self._recent, default=0.0) < config.WAKE_MIN_PEAK:
            return False
        return self.last_score >= self.threshold
