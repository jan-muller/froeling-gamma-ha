"""The long-running bridge: bytes -> frames -> readings -> MQTT.

Responsibilities
* keep the byte source open (serial reconnect with back-off);
* publish Home Assistant discovery configs on every (re)connect;
* publish a reading when its value changes, and re-publish everything every
  ``republish_interval`` seconds so HA can detect stale data via ``expire_after``;
* flip the bridge availability to ``offline`` when no valid frame arrived for
  ``stale_timeout`` seconds (entities become *unavailable*, never a false OFF);
* expose bridge statistics (frame counters, CRC errors).
"""

from __future__ import annotations

import json
import logging
import signal
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .decode import Reading, decode
from .discovery import Topics, discovery_messages
from .protocol import FrameParser
from .record import FrameRecorder

log = logging.getLogger(__name__)


@dataclass
class BridgeConfig:
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_client_id: str = "gamma2mqtt"
    topic_prefix: str = "gamma2mqtt"
    discovery_prefix: str = "homeassistant"
    device_id: str = "gamma23b"
    device_name: str = "Fröling Gamma 23 B"
    stale_timeout: float = 60.0
    republish_interval: float = 300.0
    expire_after: int = 900
    publish_raw: bool = False
    reconnect_delay: float = 5.0
    record_dir: Optional[str] = None


def _make_mqtt_client(client_id: str):
    import paho.mqtt.client as mqtt

    if hasattr(mqtt, "CallbackAPIVersion"):  # paho-mqtt >= 2.0
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    else:  # paho-mqtt 1.x (Debian/Raspberry Pi OS packages)
        client = mqtt.Client(client_id=client_id)
    return client


class Bridge:
    def __init__(self, source: Any, config: BridgeConfig, mqtt_client: Any = None) -> None:
        self.source = source
        self.cfg = config
        self.topics = Topics(config.topic_prefix, config.discovery_prefix, config.device_id)
        self.parser = FrameParser()
        self.client = mqtt_client if mqtt_client is not None else _make_mqtt_client(config.mqtt_client_id)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.values: Dict[str, Reading] = {}
        self.last_frame_at: Optional[float] = None
        self.last_publish_at: Dict[str, float] = {}
        self.online: Optional[bool] = None
        self.frames_total = 0
        self.frame_kinds: Dict[str, int] = {}
        self._minute_window: list = []
        self._connected = False
        self.recorder = FrameRecorder(config.record_dir) if config.record_dir else None

    # ------------------------------------------------------------------ MQTT
    def _setup_mqtt(self) -> None:
        c = self.client
        if self.cfg.mqtt_user:
            c.username_pw_set(self.cfg.mqtt_user, self.cfg.mqtt_password)
        c.will_set(self.topics.availability, "offline", qos=1, retain=True)
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        code = getattr(rc, "value", rc)
        if code != 0:
            log.error("MQTT connect failed: %s", rc)
            return
        log.info("MQTT connected to %s:%d", self.cfg.mqtt_host, self.cfg.mqtt_port)
        self._connected = True
        self.publish_discovery()
        with self._lock:
            self.online = None  # force availability republish
            self._update_availability(force=True)
            for reading in self.values.values():
                self._publish_reading(reading)
        self._publish_bridge_state()

    def _on_disconnect(self, client, userdata, *args) -> None:
        self._connected = False
        log.warning("MQTT disconnected; paho will reconnect automatically")

    def publish_discovery(self) -> None:
        count = 0
        for topic, payload in discovery_messages(self.topics, self.cfg.device_name, self.cfg.expire_after):
            self.client.publish(topic, payload, qos=1, retain=True)
            count += 1
        log.info("Published %d discovery configs under %s/", count, self.cfg.discovery_prefix)

    def _publish_reading(self, reading: Reading) -> None:
        f = reading.field
        value = reading.value
        if isinstance(value, bool):
            state = "ON" if value else "OFF"
        elif isinstance(value, float):
            state = f"{value:g}"
        else:
            state = str(value)
        self.client.publish(self.topics.state(f.key), state, qos=0, retain=True)
        attrs = {
            "confidence": f.confidence,
            "telegram": f.kind,
            "position": f"P{f.position}",
            "source": f"{reading.frame.source:02X}",
            "raw": reading.raw,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        self.client.publish(self.topics.attributes(f.key), json.dumps(attrs), qos=0, retain=True)
        self.last_publish_at[f.key] = time.monotonic()

    def _publish_bridge_state(self) -> None:
        now = time.monotonic()
        self._minute_window = [t for t in self._minute_window if now - t < 60]
        payload = {
            "frames_total": self.frames_total,
            "crc_errors": self.parser.rejected,
            "frames_per_minute": len(self._minute_window),
            "frame_kinds": self.frame_kinds,
            "last_frame_age": None if self.last_frame_at is None else round(now - self.last_frame_at, 1),
        }
        self.client.publish(self.topics.bridge_state, json.dumps(payload), qos=0, retain=True)

    def _update_availability(self, force: bool = False) -> None:
        now = time.monotonic()
        fresh = self.last_frame_at is not None and now - self.last_frame_at < self.cfg.stale_timeout
        if force or fresh != self.online:
            self.online = fresh
            self.client.publish(self.topics.availability, "online" if fresh else "offline", qos=1, retain=True)
            log.info("Availability -> %s", "online" if fresh else "offline")

    # -------------------------------------------------------------- pipeline
    def handle_bytes(self, data: bytes) -> None:
        """Feed raw bytes; publishes changed readings. Safe to call from tests."""
        for frame in self.parser.feed(data):
            now = time.monotonic()
            self.last_frame_at = now
            self.frames_total += 1
            self.frame_kinds[frame.kind] = self.frame_kinds.get(frame.kind, 0) + 1
            self._minute_window.append(now)
            if self.recorder is not None:
                self.recorder.write(frame)
            if self.cfg.publish_raw:
                self.client.publish(self.topics.raw(frame.kind),
                                    f"{frame.route} {frame.payload.hex(' ')}", qos=0, retain=False)
            for reading in decode(frame):
                with self._lock:
                    previous = self.values.get(reading.key)
                    changed = previous is None or previous.value != reading.value
                    self.values[reading.key] = reading
                    if changed:
                        log.info("%-28s %s   [%s %s]", reading.key, reading.value,
                                 reading.field.position_label, reading.field.confidence)
                        self._publish_reading(reading)
        with self._lock:
            self._update_availability()

    def _periodic(self) -> None:
        now = time.monotonic()
        with self._lock:
            self._update_availability()
            for key, reading in self.values.items():
                if now - self.last_publish_at.get(key, 0) >= self.cfg.republish_interval:
                    self._publish_reading(reading)
        self._publish_bridge_state()

    # ------------------------------------------------------------------ main
    def stop(self, *_: object) -> None:
        self._stop.set()

    def run(self) -> int:
        self._setup_mqtt()
        self.client.connect_async(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=30)
        self.client.loop_start()
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        last_periodic = time.monotonic()
        try:
            while not self._stop.is_set():
                try:
                    with self.source:
                        while not self._stop.is_set():
                            data = self.source.read()
                            if data:
                                self.handle_bytes(data)
                            if time.monotonic() - last_periodic >= 10:
                                self._periodic()
                                last_periodic = time.monotonic()
                            if getattr(self.source, "finished", False):
                                log.info("Replay finished")
                                self._stop.set()
                except (OSError, ValueError) as exc:
                    if self._stop.is_set():
                        break
                    log.error("Source error: %s; retrying in %.0fs", exc, self.cfg.reconnect_delay)
                    with self._lock:
                        self._update_availability()
                    self._stop.wait(self.cfg.reconnect_delay)
        finally:
            if self.recorder is not None:
                self.recorder.close()
            with self._lock:
                self.online = False
                self.client.publish(self.topics.availability, "offline", qos=1, retain=True)
            self.client.loop_stop()
            self.client.disconnect()
            log.info("Bridge stopped. frames=%d crc_errors=%d", self.frames_total, self.parser.rejected)
        return 0
