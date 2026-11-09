"""Command-line entry point: `python -m home_manager --config config/devices.json`."""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from .config import ConfigError, load_config
from .controller import HomeController
from .relays import make_driver
from .voice import Speaker, WakeWordGate, keyboard_phrases, microphone_phrases


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="home-manager", description="Voice-controlled home switches")
    p.add_argument("-c", "--config", default="config/devices.json", help="device config file")
    p.add_argument("--keyboard", action="store_true", help="type commands instead of speaking")
    p.add_argument("--driver", choices=["mock", "gpio"], help="override the relay driver")
    p.add_argument("--engine", choices=["google", "vosk"], default="google",
                   help="speech recogniser (vosk = offline)")
    p.add_argument("--vosk-model", help="path to a downloaded Vosk model")
    p.add_argument("--no-tts", action="store_true", help="print replies instead of speaking")
    p.add_argument("--no-wake-word", action="store_true",
                   help="treat every phrase as a command")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    if args.driver:
        config.driver = args.driver

    controller = HomeController(config, make_driver(config.driver, config.devices))
    speaker = Speaker(enabled=not args.no_tts)
    gate = None if (args.no_wake_word or args.keyboard) else WakeWordGate(config.wake_word)

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)

    phrases = (keyboard_phrases() if args.keyboard
               else microphone_phrases(config.language, args.engine, args.vosk_model))
    if args.keyboard:
        print("Type a command, e.g. 'turn on the kitchen light'. Ctrl+D to quit.")
    else:
        print(f"Say '{config.wake_word}' followed by a command.")

    try:
        for phrase in phrases:
            command = gate.filter(phrase) if gate else phrase
            if command is None:
                continue
            if command == "":
                speaker.say("Yes?")
                continue
            speaker.say(controller.handle(command))
    except KeyboardInterrupt:
        pass
    finally:
        controller.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
