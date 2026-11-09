"""Relay drivers: the hardware layer that actually switches the mains circuits."""

from __future__ import annotations

import logging
from typing import Protocol

from .config import Device

log = logging.getLogger(__name__)


class RelayDriver(Protocol):
    def set(self, device: Device, on: bool) -> None: ...
    def close(self) -> None: ...


class MockRelayDriver:
    """In-memory driver for development and tests (no hardware needed)."""

    def __init__(self) -> None:
        self.pins: dict[int, bool] = {}

    def set(self, device: Device, on: bool) -> None:
        self.pins[device.pin] = on
        log.info("[mock] GPIO %s -> %s (%s)", device.pin, "ON" if on else "OFF", device.id)

    def close(self) -> None:
        self.pins.clear()


class GpioRelayDriver:
    """Drives a relay board from Raspberry Pi GPIO pins using gpiozero.

    Pin numbers in the config are BCM numbers.
    """

    def __init__(self, devices: list[Device]) -> None:
        try:
            from gpiozero import OutputDevice  # type: ignore
        except ImportError as exc:  # pragma: no cover - only on hardware
            raise RuntimeError(
                "gpiozero is not installed. Run: pip install 'home-manager[pi]'"
            ) from exc
        self._outputs = {
            d.pin: OutputDevice(d.pin, active_high=not d.active_low, initial_value=False)
            for d in devices
        }

    def set(self, device: Device, on: bool) -> None:  # pragma: no cover - hardware
        out = self._outputs[device.pin]
        out.on() if on else out.off()

    def close(self) -> None:  # pragma: no cover - hardware
        for out in self._outputs.values():
            out.off()
            out.close()


def make_driver(kind: str, devices: list[Device]) -> RelayDriver:
    if kind == "gpio":
        return GpioRelayDriver(devices)
    return MockRelayDriver()
