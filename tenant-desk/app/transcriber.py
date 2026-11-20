"""Speech-to-text for voice notes.

Transcriber is the interface: anything with transcribe(path) -> str.
FasterWhisperTranscriber runs Whisper locally on the CPU (install it
from requirements-voice.txt). FakeTranscriber is used in tests.
"""
from typing import Protocol


class Transcriber(Protocol):
    def transcribe(self, audio_path: str) -> str: ...


class FasterWhisperTranscriber:
    def __init__(self, model_size="base"):
        self.model_size = model_size
        self._model = None  # loaded on first use, it takes a few seconds

    def _load(self):
        # Imported here so the app and tests run without faster-whisper installed.
        from faster_whisper import WhisperModel
        self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio_path):
        if self._model is None:
            self._load()
        segments, _info = self._model.transcribe(str(audio_path))
        return " ".join(segment.text.strip() for segment in segments)


class FakeTranscriber:
    """Returns the same text for every file and remembers which files it got."""

    def __init__(self, text="the boiler is broken"):
        self.text = text
        self.paths = []

    def transcribe(self, audio_path):
        self.paths.append(str(audio_path))
        return self.text
