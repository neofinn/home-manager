import json

import pytest

from home_manager.config import ConfigError, parse_config
from home_manager.controller import HomeController
from home_manager.parser import CommandParser
from home_manager.relays import MockRelayDriver
from home_manager.voice import WakeWordGate

CONFIG = {
    "wake_word": "home manager",
    "devices": [
        {"id": "living_light", "name": "light", "room": "living room", "pin": 17,
         "aliases": ["hall light"]},
        {"id": "living_fan", "name": "fan", "room": "living room", "pin": 27},
        {"id": "bedroom_light", "name": "light", "room": "bedroom", "pin": 22},
        {"id": "bedroom_fan", "name": "fan", "room": "bedroom", "pin": 23},
        {"id": "kitchen_light", "name": "light", "room": "kitchen", "pin": 24},
        {"id": "geyser", "name": "geyser", "room": "bathroom", "pin": 25,
         "aliases": ["water heater"]},
    ],
}


@pytest.fixture
def config(tmp_path):
    cfg = parse_config(CONFIG)
    cfg.state_file = str(tmp_path / "state.json")
    return cfg


@pytest.fixture
def parser(config):
    return CommandParser(config)


@pytest.fixture
def home(config):
    return HomeController(config, MockRelayDriver())


@pytest.mark.parametrize("text, action, ids", [
    ("turn on the kitchen light", "on", ["kitchen_light"]),
    ("Kitchen light ON please", "on", ["kitchen_light"]),
    ("bedroom fan off", "off", ["bedroom_fan"]),
    ("switch off the hall light", "off", ["living_light"]),
    ("turn on the water heater", "on", ["geyser"]),
    ("toggle the geyser", "toggle", ["geyser"]),
    ("turn off all lights", "off", ["living_light", "bedroom_light", "kitchen_light"]),
    ("turn on all the fans", "on", ["living_fan", "bedroom_fan"]),
    ("turn off the living room", "off", ["living_light", "living_fan"]),
    ("living room fan on", "on", ["living_fan"]),
    ("turn off everything", "off", [d["id"] for d in CONFIG["devices"]]),
    # Hindi / Hinglish
    ("kitchen ki batti band karo", "off", ["kitchen_light"]),
    ("bedroom ka pankha chalu karo", "on", ["bedroom_fan"]),
    ("sab band karo", "off", [d["id"] for d in CONFIG["devices"]]),
    # wake word inside the sentence is ignored
    ("home manager turn on the geyser", "on", ["geyser"]),
])
def test_parse_commands(parser, text, action, ids):
    intent = parser.parse(text)
    assert intent.ok, intent.error
    assert intent.action == action
    assert sorted(intent.device_ids) == sorted(ids)


@pytest.mark.parametrize("text", [
    "turn on the light",   # light exists in three rooms
    "turn on",             # no device
    "kitchen light",       # no action
    "turn on off the fan",  # contradictory
])
def test_parse_needs_clarification(parser, text):
    assert not parser.parse(text).ok


def test_status_questions(parser):
    assert parser.parse("what is on").action == "status"
    intent = parser.parse("is the kitchen light on?")
    assert intent.action == "status" and intent.device_ids == ["kitchen_light"]


def test_controller_switches_relays_and_reports(home):
    assert home.handle("turn on the kitchen light") == "Kitchen light turned on."
    assert home.driver.pins[24] is True
    assert home.state["kitchen_light"] is True
    assert "Kitchen light" in home.handle("what is on")

    home.handle("toggle the kitchen light")
    assert home.driver.pins[24] is False
    assert home.handle("what is on") == "Everything is off."


def test_controller_returns_clarifying_question(home):
    reply = home.handle("turn on the fan")
    assert reply.startswith("Which one?")
    assert not any(home.state.values())


def test_state_persists_across_restart(config):
    first = HomeController(config, MockRelayDriver())
    first.handle("turn on all fans")
    saved = json.loads(open(config.state_file).read())
    assert saved["bedroom_fan"] is True

    driver = MockRelayDriver()
    second = HomeController(config, driver)
    assert second.state["living_fan"] is True
    assert driver.pins[27] is True  # relay physically restored


def test_wake_word_gate():
    gate = WakeWordGate("home manager")
    assert gate.filter("turn on the fan") is None
    assert gate.filter("Home Manager, turn on the fan") == "turn on the fan"
    assert gate.filter("home manager") == ""
    assert gate.filter("fan on") == "fan on"
    assert gate.filter("fan off") is None  # only one follow-up phrase


@pytest.mark.parametrize("bad", [
    {},
    {"devices": []},
    {"devices": [{"id": "a", "name": "x"}]},  # missing pin
    {"devices": [{"id": "a", "name": "x", "pin": 1}, {"id": "a", "name": "y", "pin": 2}]},
    {"devices": [{"id": "a", "name": "x", "pin": 1}, {"id": "b", "name": "y", "pin": 1}]},
    {"devices": [{"id": "a", "name": "x", "pin": 1}], "driver": "zigbee"},
])
def test_invalid_config(bad):
    with pytest.raises(ConfigError):
        parse_config(bad)
