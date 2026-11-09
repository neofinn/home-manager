"""Microphone input (speech-to-text) and spoken replies (text-to-speech).

Everything here is optional: if the audio libraries are not installed the app
falls back to keyboard input and printed replies, which is handy for testing.
"""

from __future__ import annotations

import logging
from typing import Iterator

log = logging.getLogger(__name__)


class Speaker:
    """Speaks replies with pyttsx3 (offline) when available, otherwise prints them."""

    def __init__(self, enabled: bool = True) -> None:
        self._engine = None
        if enabled:
            try:
                import pyttsx3  # type: ignore

                self._engine = pyttsx3.init()
            except Exception as exc:  # pragma: no cover - depends on system audio
                log.info("Text-to-speech unavailable (%s); printing replies.", exc)

    def say(self, text: str) -> None:
        print(f"🔊 {text}")
        if self._engine is not None:  # pragma: no cover - audio
            self._engine.say(text)
            self._engine.runAndWait()


def keyboard_phrases(prompt: str = "🎤 > ") -> Iterator[str]:
    """Typed commands, for development without a microphone."""
    while True:
        try:
            line = input(prompt)
        except EOFError:
            return
        if line.strip():
            yield line.strip()


def microphone_phrases(language: str = "en-IN", engine: str = "google",
                       vosk_model: str | None = None) -> Iterator[str]:  # pragma: no cover
    """Continuously listen on the default microphone and yield recognised phrases.

    engine="google" uses Google's free web recogniser (needs internet).
    engine="vosk" runs fully offline; pass the path of a downloaded Vosk model.
    """
    try:
        import speech_recognition as sr  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "SpeechRecognition is not installed. Run: pip install 'home-manager[voice]'"
        ) from exc

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    vosk = None
    if engine == "vosk":
        import json

        from vosk import KaldiRecognizer, Model  # type: ignore

        vosk = (Model(vosk_model) if vosk_model else Model(lang="en-in")), KaldiRecognizer, json

    with sr.Microphone() as source:
        log.info("Calibrating for background noise...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        log.info("Listening.")
        while True:
            try:
                audio = recognizer.listen(source, phrase_time_limit=6)
            except sr.WaitTimeoutError:
                continue
            try:
                if vosk:
                    model, kaldi, json_mod = vosk
                    rec = kaldi(model, audio.sample_rate)
                    rec.AcceptWaveform(audio.get_raw_data())
                    text = json_mod.loads(rec.FinalResult()).get("text", "")
                else:
                    text = recognizer.recognize_google(audio, language=language)
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                log.warning("Speech service error: %s", exc)
                continue
            if text:
                log.debug("Recognised: %s", text)
                yield text


class WakeWordGate:
    """Only pass on commands addressed to the assistant.

    "home manager, turn on the fan"  -> command in the same breath
    "home manager" ... "fan on"      -> command in the next phrase
    """

    def __init__(self, wake_word: str, follow_up_phrases: int = 1) -> None:
        self.wake_word = wake_word.lower()
        self.follow_up = follow_up_phrases
        self._armed = 0

    def filter(self, phrase: str) -> str | None:
        lower = phrase.lower()
        if self.wake_word and self.wake_word in lower:
            rest = lower.split(self.wake_word, 1)[1].strip(" ,.!?")
            if rest:
                self._armed = 0
                return rest
            self._armed = self.follow_up
            return ""  # wake word alone: acknowledge and wait
        if self._armed > 0:
            self._armed -= 1
            return phrase
        return None
