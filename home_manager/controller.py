"""Executes intents against the relays and keeps track of which switches are on."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from .config import Config
from .parser import CommandParser, Intent
from .relays import RelayDriver

log = logging.getLogger(__name__)


class HomeController:
    def __init__(self, config: Config, driver: RelayDriver, restore_state: bool = True) -> None:
        self.config = config
        self.driver = driver
        self.parser = CommandParser(config)
        self.state: dict[str, bool] = {d.id: False for d in config.devices}
        self._lock = threading.Lock()
        self._state_path = Path(config.state_file) if config.state_file else None
        if restore_state:
            self._restore()

    # ------------------------------------------------------------------ public

    def handle(self, text: str) -> str:
        """Parse a spoken sentence, act on it, and return a reply to speak back."""
        intent = self.parser.parse(text)
        log.info("Heard %r -> %s", text, intent)
        return self.execute(intent)

    def execute(self, intent: Intent) -> str:
        if not intent.ok:
            return intent.error
        if intent.action == "status":
            return self.describe(intent.device_ids)

        changed = []
        with self._lock:
            for dev_id in intent.device_ids:
                new = not self.state[dev_id] if intent.action == "toggle" else intent.action == "on"
                self._apply(dev_id, new)
                changed.append((dev_id, new))
            self._save()

        if len(changed) == 1:
            dev_id, on = changed[0]
            return f"{self._label(dev_id)} turned {'on' if on else 'off'}."
        if intent.action == "toggle":
            return f"Toggled {len(changed)} devices."
        return f"Turned {intent.action} {len(changed)} devices."

    def set(self, device_id: str, on: bool) -> None:
        with self._lock:
            self._apply(device_id, on)
            self._save()

    def describe(self, device_ids: list[str] | None = None) -> str:
        ids = device_ids or list(self.state)
        on = [self._label(i) for i in ids if self.state[i]]
        if not on:
            return "Everything is off." if len(ids) > 1 else f"{self._label(ids[0])} is off."
        return "On: " + ", ".join(on) + "."

    def shutdown(self) -> None:
        self.driver.close()

    # ----------------------------------------------------------------- private

    def _label(self, dev_id: str) -> str:
        d = self.config.device_by_id(dev_id)
        return f"{d.room} {d.name}".strip().capitalize()

    def _apply(self, dev_id: str, on: bool) -> None:
        self.driver.set(self.config.device_by_id(dev_id), on)
        self.state[dev_id] = on

    def _save(self) -> None:
        if not self._state_path:
            return
        try:
            self._state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        except OSError as exc:
            log.warning("Could not save state: %s", exc)

    def _restore(self) -> None:
        if not self._state_path or not self._state_path.exists():
            return
        try:
            saved = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Ignoring unreadable state file: %s", exc)
            return
        for dev_id, on in saved.items():
            if dev_id in self.state:
                self._apply(dev_id, bool(on))
