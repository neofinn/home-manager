# Home Manager

A voice-controlled switch controller for your house. It sits on the house's
switch wiring through a relay board and turns lights, fans, sockets and other
loads on and off when you speak to it.

```
"Home manager, turn on the kitchen light"   →  Kitchen light turned on.
"Home manager, bedroom ka pankha chalu karo" →  Bedroom fan turned on.
"Home manager, sab band karo"                →  Turned off 8 devices.
"Home manager, what is on?"                  →  On: Living room fan.
```

## How it works

```
 Microphone ──► speech-to-text ──► wake word ──► command parser ──► controller ──► relay driver ──► relay board ──► mains switch line
 (USB mic)      (Google / Vosk)    "home manager"  (English+Hindi)   (state.json)   (GPIO pins)                        (light, fan…)
                                                                         │
 Speaker ◄── text-to-speech ◄────────── reply ◄──────────────────────────┘
```

| Module | Job |
|---|---|
| `home_manager/voice.py` | Microphone listening, wake-word gate, spoken replies |
| `home_manager/parser.py` | Turns a sentence into an intent: on / off / toggle / status + which devices |
| `home_manager/controller.py` | Switches relays, remembers state across restarts, builds the reply |
| `home_manager/relays.py` | `gpio` driver for a Raspberry Pi relay board, `mock` driver for testing |
| `config/devices.json` | Your rooms, devices, GPIO pins and nicknames |

## What you can say

- **On / off:** "turn on the kitchen light", "bedroom fan off", "switch off the hall light"
- **Toggle:** "toggle the geyser"
- **Groups:** "turn off all lights", "turn on all fans", "turn off the living room", "turn off everything"
- **Status:** "what is on?", "is the geyser on?"
- **Hindi / Hinglish:** *batti* (light), *pankha* (fan), *chalu / jalao* (on), *band / bujhao* (off), *sab* (all) —
  e.g. "kitchen ki batti band karo"
- If a request is ambiguous ("turn on the fan" with fans in two rooms) it asks
  *"Which one? I found it in: bedroom, living room."* instead of guessing.

Say the wake word and command together ("home manager, fan on"), or say
"home manager", wait for "Yes?", then give the command.

## Hardware

- Raspberry Pi (3B+, 4 or 5) running Raspberry Pi OS
- USB microphone (or a USB/I²S mic array) and a small speaker
- Relay module with one channel per switch (5 V, opto-isolated, rated for at
  least 10 A / 250 VAC), or solid-state relays for fans and lights
- 5 V power supply for the Pi, mounted in a proper enclosure

Each relay channel is wired **in parallel with** (two-way) or **in place of**
the existing wall switch on the **live (phase)** wire of that circuit. The GPIO
pin numbers in `config/devices.json` are BCM numbers.

> ⚠️ **Mains electricity can kill.** Have a licensed electrician do the
> 230 V / 120 V wiring, switch off the breaker before working, use relays rated
> for the load (geysers, ACs and motors need contactors or higher-rated relays),
> fuse each circuit, keep low-voltage and mains wiring physically separated, and
> keep the original wall switches working as a manual override.

## Setup

```bash
git clone <this repo> home-manager && cd home-manager
python3 -m venv .venv && . .venv/bin/activate

pip install -e '.[dev]'            # core + tests (no hardware needed)
pip install -e '.[voice]'          # microphone + text-to-speech
pip install -e '.[pi]'             # Raspberry Pi GPIO
pip install -e '.[offline]'        # optional: offline recognition with Vosk
# On Raspberry Pi OS you may first need: sudo apt install portaudio19-dev espeak-ng
```

Edit `config/devices.json` to match your house:

```json
{ "id": "bedroom_fan", "name": "fan", "room": "bedroom", "pin": 23, "aliases": ["pankha"] }
```

- `active_low` (default `true`) — set to `false` if your relay board switches on a HIGH signal.
- `driver` — `mock` (prints only) or `gpio` (real relays).
- `wake_word`, `language` (e.g. `en-IN`, `hi-IN`), `state_file` are also configurable.

## Running

```bash
python -m home_manager --keyboard                 # type commands, mock relays — try it on any PC
python -m home_manager                            # listen on the microphone (Google recogniser)
python -m home_manager --engine vosk --vosk-model ./model   # fully offline recognition
python -m home_manager --driver gpio              # drive the real relay board
```

Start automatically at boot on the Pi:

```bash
sudo cp deploy/home-manager.service /etc/systemd/system/
sudo systemctl enable --now home-manager
journalctl -u home-manager -f
```

Switch states are saved to `state.json` and restored after a power cut or reboot.

## Tests

```bash
pytest
```
