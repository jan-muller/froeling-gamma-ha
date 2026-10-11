"""Command line entry point. Every option can also be given as an environment
variable (``GAMMA_<OPTION>``), which is how the systemd unit configures it."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional

from .bridge import Bridge, BridgeConfig
from .sources import ReplaySource, SerialSource


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(f"GAMMA_{name.upper()}", default)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="gamma2mqtt",
        description="Passive EBV Gamma 23 B RS485 reader -> Home Assistant MQTT Discovery. "
                    "Never transmits on the bus.")
    src = ap.add_argument_group("source")
    src.add_argument("--port", default=_env("PORT", "/dev/ttyUSB0"),
                     help="serial port, prefer /dev/serial/by-id/... (default: %(default)s)")
    src.add_argument("--replay", default=_env("REPLAY"), metavar="CSV",
                     help="replay a gamma_frames*.csv capture instead of reading the serial port")
    src.add_argument("--replay-speed", type=float, default=float(_env("REPLAY_SPEED", "1")),
                     help="replay speed factor (default: %(default)s)")
    src.add_argument("--replay-loop", action="store_true", default=_env("REPLAY_LOOP") == "1",
                     help="restart the replay file when exhausted")

    m = ap.add_argument_group("mqtt")
    m.add_argument("--mqtt-host", default=_env("MQTT_HOST", "localhost"))
    m.add_argument("--mqtt-port", type=int, default=int(_env("MQTT_PORT", "1883")))
    m.add_argument("--mqtt-user", default=_env("MQTT_USER"))
    m.add_argument("--mqtt-password", default=_env("MQTT_PASSWORD"))
    m.add_argument("--mqtt-client-id", default=_env("MQTT_CLIENT_ID", "gamma2mqtt"))
    m.add_argument("--topic-prefix", default=_env("TOPIC_PREFIX", "gamma2mqtt"))
    m.add_argument("--discovery-prefix", default=_env("DISCOVERY_PREFIX", "homeassistant"))
    m.add_argument("--device-id", default=_env("DEVICE_ID", "gamma23b"))
    m.add_argument("--device-name", default=_env("DEVICE_NAME", "Fröling Gamma 23 B"))
    m.add_argument("--publish-raw", action="store_true", default=_env("PUBLISH_RAW") == "1",
                   help="also publish every frame payload under <prefix>/raw/<kind>")

    t = ap.add_argument_group("timing")
    t.add_argument("--stale-timeout", type=float, default=float(_env("STALE_TIMEOUT", "60")),
                   help="seconds without a valid frame before availability goes offline")
    t.add_argument("--republish-interval", type=float,
                   default=float(_env("REPUBLISH_INTERVAL", "300")),
                   help="seconds between forced re-publishes of unchanged values")
    t.add_argument("--expire-after", type=int, default=int(_env("EXPIRE_AFTER", "900")),
                   help="HA expire_after for sensors (should exceed republish interval)")

    ap.add_argument("--log-level", default=_env("LOG_LEVEL", "INFO"))
    ap.add_argument("--print-discovery", action="store_true",
                    help="print discovery payloads and exit")
    return ap


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    cfg = BridgeConfig(
        mqtt_host=args.mqtt_host, mqtt_port=args.mqtt_port,
        mqtt_user=args.mqtt_user, mqtt_password=args.mqtt_password,
        mqtt_client_id=args.mqtt_client_id,
        topic_prefix=args.topic_prefix, discovery_prefix=args.discovery_prefix,
        device_id=args.device_id, device_name=args.device_name,
        stale_timeout=args.stale_timeout, republish_interval=args.republish_interval,
        expire_after=args.expire_after, publish_raw=args.publish_raw,
    )

    if args.print_discovery:
        from .discovery import Topics, discovery_messages
        topics = Topics(cfg.topic_prefix, cfg.discovery_prefix, cfg.device_id)
        for topic, payload in discovery_messages(topics, cfg.device_name, cfg.expire_after):
            print(topic)
            print("  ", payload)
        return 0

    if args.replay:
        source = ReplaySource(args.replay, speed=args.replay_speed, loop=args.replay_loop)
    else:
        source = SerialSource(args.port)

    return Bridge(source, cfg).run()


if __name__ == "__main__":
    sys.exit(main())
