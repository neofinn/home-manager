"""Load and validate the device configuration file."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """Raised when the configuration file is invalid."""


@dataclass(frozen=True)
class Device:
    """One switchable load (light, fan, socket...) wired through a relay channel."""

    id: str
    name: str
    pin: int
    room: str = ""
    aliases: tuple[str, ...] = ()
    # Most cheap relay boards are "active low": the coil energises when the pin is LOW.
    active_low: bool = True

    def all_names(self) -> list[str]:
        """Every phrase that can refer to this device, lower-cased."""
        names = {self.name.lower(), *(a.lower() for a in self.aliases)}
        if self.room:
            names.add(f"{self.room} {self.name}".lower())
        return sorted(names)


@dataclass
class Config:
    devices: list[Device]
    wake_word: str = "home manager"
    driver: str = "mock"  # "mock" or "gpio"
    state_file: str = "state.json"
    language: str = "en-IN"
    extra: dict = field(default_factory=dict)

    def device_by_id(self, device_id: str) -> Device:
        for d in self.devices:
            if d.id == device_id:
                return d
        raise KeyError(device_id)

    @property
    def rooms(self) -> list[str]:
        return sorted({d.room.lower() for d in self.devices if d.room})


def load_config(path: str | Path) -> Config:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is not valid JSON: {exc}") from exc
    return parse_config(raw)


def parse_config(raw: dict) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be an object")
    devices_raw = raw.get("devices")
    if not isinstance(devices_raw, list) or not devices_raw:
        raise ConfigError("Config must contain a non-empty 'devices' list")

    devices: list[Device] = []
    seen_ids: set[str] = set()
    seen_pins: set[int] = set()
    for i, d in enumerate(devices_raw):
        try:
            dev = Device(
                id=str(d["id"]),
                name=str(d["name"]),
                pin=int(d["pin"]),
                room=str(d.get("room", "")),
                aliases=tuple(str(a) for a in d.get("aliases", [])),
                active_low=bool(d.get("active_low", True)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"Device #{i} is missing or has an invalid field: {exc}") from exc
        if dev.id in seen_ids:
            raise ConfigError(f"Duplicate device id: {dev.id}")
        if dev.pin in seen_pins:
            raise ConfigError(f"GPIO pin {dev.pin} is assigned to more than one device")
        seen_ids.add(dev.id)
        seen_pins.add(dev.pin)
        devices.append(dev)

    driver = raw.get("driver", "mock")
    if driver not in ("mock", "gpio"):
        raise ConfigError("driver must be 'mock' or 'gpio'")

    return Config(
        devices=devices,
        wake_word=str(raw.get("wake_word", "home manager")).lower(),
        driver=driver,
        state_file=str(raw.get("state_file", "state.json")),
        language=str(raw.get("language", "en-IN")),
        extra={k: v for k, v in raw.items()
               if k not in {"devices", "wake_word", "driver", "state_file", "language"}},
    )
