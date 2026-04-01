"""VoiceRecognizer - voice input capture and transcription."""

from __future__ import annotations

import importlib
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional


class RecognizerBackend(Enum):
    """Supported speech recognition backends."""

    WHISPER = "whisper"             # OpenAI Whisper (local)
    SPEECH_RECOGNITION = "sr"      # SpeechRecognition library
    SYSTEM = "system"              # OS-level dictation
    NONE = "none"


class RecognizerState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    ERROR = "error"


@dataclass
class TranscriptSegment:
    """A segment of transcribed speech."""

    text: str
    confidence: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0
    is_final: bool = True


class VoiceRecognizer:
    """Manages voice input capture and transcription.

    Supports multiple backends and provides a unified interface for
    starting/stopping listening and retrieving transcripts.
    """

    def __init__(
        self,
        backend: Optional[RecognizerBackend] = None,
        language: str = "en-US",
        on_transcript: Optional[Callable[[TranscriptSegment], None]] = None,
    ) -> None:
        self._backend = backend or self._detect_backend()
        self._language = language
        self._state = RecognizerState.IDLE
        self._segments: list[TranscriptSegment] = []
        self._on_transcript = on_transcript
        self._listen_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._error: Optional[str] = None

    @staticmethod
    def _detect_backend() -> RecognizerBackend:
        """Auto-detect the best available backend."""
        # Check for whisper
        try:
            importlib.import_module("whisper")
            return RecognizerBackend.WHISPER
        except ImportError:
            pass
        # Check for SpeechRecognition
        try:
            importlib.import_module("speech_recognition")
            return RecognizerBackend.SPEECH_RECOGNITION
        except ImportError:
            pass
        # Check for system-level dictation (macOS)
        if shutil.which("say"):  # macOS proxy check
            return RecognizerBackend.SYSTEM
        return RecognizerBackend.NONE

    @property
    def state(self) -> RecognizerState:
        return self._state

    @property
    def backend(self) -> RecognizerBackend:
        return self._backend

    @property
    def error(self) -> Optional[str]:
        return self._error

    def is_available(self) -> bool:
        """Check if voice recognition is available on this system."""
        if self._backend == RecognizerBackend.NONE:
            return False
        if self._backend == RecognizerBackend.WHISPER:
            try:
                importlib.import_module("whisper")
                return True
            except ImportError:
                return False
        if self._backend == RecognizerBackend.SPEECH_RECOGNITION:
            try:
                sr = importlib.import_module("speech_recognition")
                # Check if microphone is available
                mic_class = getattr(sr, "Microphone", None)
                return mic_class is not None
            except ImportError:
                return False
        return self._backend == RecognizerBackend.SYSTEM

    def start_listening(self) -> bool:
        """Begin listening for voice input.

        Returns:
            True if listening started successfully.
        """
        if self._state == RecognizerState.LISTENING:
            return True
        if not self.is_available():
            self._error = f"Backend {self._backend.value} is not available"
            self._state = RecognizerState.ERROR
            return False

        self._stop_event.clear()
        self._segments.clear()
        self._error = None
        self._state = RecognizerState.LISTENING

        if self._backend == RecognizerBackend.SPEECH_RECOGNITION:
            self._listen_thread = threading.Thread(
                target=self._sr_listen_loop, daemon=True
            )
            self._listen_thread.start()
            return True

        # For other backends, just mark as listening
        return True

    def _sr_listen_loop(self) -> None:
        """Background listening loop using SpeechRecognition."""
        try:
            sr = importlib.import_module("speech_recognition")
            recognizer = sr.Recognizer()
            mic = sr.Microphone()
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                while not self._stop_event.is_set():
                    try:
                        audio = recognizer.listen(source, timeout=2, phrase_time_limit=10)
                        self._state = RecognizerState.PROCESSING
                        text = recognizer.recognize_google(audio, language=self._language)
                        segment = TranscriptSegment(
                            text=text,
                            confidence=0.8,
                            start_time=time.time(),
                            is_final=True,
                        )
                        self._segments.append(segment)
                        if self._on_transcript:
                            self._on_transcript(segment)
                        self._state = RecognizerState.LISTENING
                    except Exception:
                        # Timeout or recognition error - keep listening
                        continue
        except Exception as e:
            self._error = str(e)
            self._state = RecognizerState.ERROR

    def stop_listening(self) -> str:
        """Stop listening and return the full transcript.

        Returns:
            The concatenated transcript text.
        """
        self._stop_event.set()
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=3)
        self._state = RecognizerState.IDLE
        return self.get_transcript()

    def get_transcript(self) -> str:
        """Get the full transcript from all segments."""
        return " ".join(seg.text for seg in self._segments if seg.text)

    def get_segments(self) -> list[TranscriptSegment]:
        """Get all transcript segments."""
        return list(self._segments)

    def clear(self) -> None:
        """Clear all transcript data."""
        self._segments.clear()
        self._error = None

    def feed_text(self, text: str) -> None:
        """Manually feed text as if it were recognized speech. Useful for testing."""
        segment = TranscriptSegment(
            text=text, confidence=1.0, start_time=time.time(), is_final=True
        )
        self._segments.append(segment)
        if self._on_transcript:
            self._on_transcript(segment)
