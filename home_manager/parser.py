"""Turn a spoken sentence into an intent (what to do, and to which devices)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import Config, Device

# Words normalised before parsing. Includes common Hindi / Hinglish words so
# commands like "kitchen ki batti band karo" or "pankha chalu karo" work.
SYNONYMS = {
    # actions
    "chalu": "on", "chalao": "on", "jalao": "on", "jala": "on", "start": "on",
    "activate": "on", "enable": "on", "open": "on",
    "band": "off", "bujhao": "off", "bujha": "off", "stop": "off",
    "deactivate": "off", "disable": "off", "shut": "off", "kill": "off",
    "switch": "turn", "put": "turn",
    # quantities
    "sab": "all", "sabhi": "all", "saare": "all", "sare": "all", "every": "all",
    "everything": "all", "anything": "all",
    # nouns
    "batti": "light", "bulb": "light", "lamp": "light", "lights": "lights",
    "pankha": "fan", "pankhe": "fans",
    "plug": "socket", "outlet": "socket",
}

ON_WORDS = {"on"}
OFF_WORDS = {"off"}
TOGGLE_WORDS = {"toggle", "flip"}
STATUS_PHRASES = ("status", "what is on", "whats on", "which", "kya on", "kaun sa")
ALL_WORDS = {"all"}

FILLER = {
    "please", "the", "a", "an", "can", "you", "could", "would", "kindly", "my",
    "in", "of", "to", "for", "me", "karo", "kar", "kardo", "do", "de", "dena",
    "ki", "ka", "ke", "wala", "wali", "and", "now", "just", "also",
}


def canon(phrase: str) -> str:
    """Normalise a device/room name exactly like spoken text, minus filler."""
    return " ".join(w for w in normalise(phrase) if w not in FILLER)


@dataclass
class Intent:
    action: str  # "on" | "off" | "toggle" | "status" | "unknown"
    device_ids: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def normalise(text: str, wake_word: str = "") -> list[str]:
    text = text.lower()
    text = text.replace("what's", "whats").replace("'", "")
    text = re.sub(r"[^a-z0-9ऀ-ॿ ]+", " ", text)
    if wake_word:
        text = re.sub(rf"\b{re.escape(wake_word.lower())}\b", " ", text)
    words = [SYNONYMS.get(w, w) for w in text.split()]
    return words


class CommandParser:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.rooms = sorted({canon(r) for r in config.rooms} - {""})
        self._names = {d.id: sorted({canon(n) for n in d.all_names()} - {""})
                       for d in config.devices}

    def parse(self, text: str) -> Intent:
        words = normalise(text, self.config.wake_word)
        joined = " ".join(words)

        if not words:
            return Intent("unknown", error="I didn't hear a command.")

        is_question = words[0] in ("is", "are", "kya")
        if is_question or any(re.search(rf"\b{p}\b", joined) for p in STATUS_PHRASES):
            return Intent("status", [d.id for d in self._match_devices(words, allow_all=True)[0]
                                     ] or [d.id for d in self.config.devices])

        action = self._action(words)
        if action is None:
            return Intent("unknown", error="Should I turn it on or off?")
        if action == "ambiguous":
            return Intent("unknown", error="I heard both on and off. Please say it again.")

        devices, err = self._match_devices(words, allow_all=True)
        if err:
            return Intent(action, error=err)
        return Intent(action, [d.id for d in devices])

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _action(words: list[str]) -> str | None:
        has_on = any(w in ON_WORDS for w in words)
        has_off = any(w in OFF_WORDS for w in words)
        has_toggle = any(w in TOGGLE_WORDS for w in words)
        if has_on and has_off:
            return "ambiguous"
        if has_on:
            return "on"
        if has_off:
            return "off"
        if has_toggle:
            return "toggle"
        return None

    def _room_in(self, text: str) -> str | None:
        # Prefer the longest room name mentioned ("master bedroom" over "bedroom").
        found = [r for r in self.rooms if re.search(rf"\b{re.escape(r)}\b", text)]
        return max(found, key=len) if found else None

    def _match_devices(self, words: list[str], allow_all: bool) -> tuple[list[Device], str]:
        meaningful = [w for w in words if w not in FILLER]
        text = " ".join(meaningful)
        room = self._room_in(text)
        wants_all = any(w in ALL_WORDS for w in meaningful)

        # Score each device by the longest of its names found in the sentence.
        scored: list[tuple[int, bool, Device]] = []
        for dev in self.config.devices:
            best, plural = 0, False
            for name in self._names[dev.id]:
                m = re.search(rf"\b{re.escape(name)}(s)?\b", text)
                if m and len(name) > best:
                    best, plural = len(name), bool(m.group(1))
            if best:
                scored.append((best, plural, dev))

        if room:
            in_room = [s for s in scored if canon(s[2].room) == room]
            if in_room:
                scored = in_room
            elif not scored:
                # "turn off the kitchen" / "kitchen all off" -> everything in that room
                return [d for d in self.config.devices if canon(d.room) == room], ""

        if not scored:
            if wants_all and allow_all:
                return list(self.config.devices), ""
            return [], "I couldn't tell which device you mean."

        plural = any(p for _, p, _ in scored)
        if wants_all or plural:
            return [d for _, _, d in scored], ""

        top = max(s[0] for s in scored)
        best = [d for score, _, d in scored if score == top]
        if len(best) > 1:
            where = ", ".join(sorted({d.room or d.name for d in best}))
            return [], f"Which one? I found it in: {where}."
        return best, ""
