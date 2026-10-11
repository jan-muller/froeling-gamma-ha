"""Home Assistant MQTT Discovery payloads.

Topic layout (``prefix`` defaults to ``gamma2mqtt``)::

    <prefix>/availability                 online | offline  (retained, LWT)
    <prefix>/<key>/state                  entity state      (retained)
    <prefix>/<key>/attributes             JSON attributes   (retained)
    <prefix>/bridge/state                 JSON bridge stats
    <prefix>/raw/<kind>                   payload hex (optional, --publish-raw)
    <discovery_prefix>/<component>/<device_id>/<key>/config
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, Tuple

from . import __version__
from .model import FIELDS, Field

BRIDGE_FIELDS = (
    ("frames_total", "Frames ontvangen", "mdi:counter", "total_increasing", None),
    ("crc_errors", "CRC-fouten", "mdi:alert-circle-outline", "total_increasing", None),
    ("frames_per_minute", "Frames per minuut", "mdi:speedometer", "measurement", "/min"),
)


class Topics:
    def __init__(self, prefix: str, discovery_prefix: str, device_id: str) -> None:
        self.prefix = prefix.rstrip("/")
        self.discovery_prefix = discovery_prefix.rstrip("/")
        self.device_id = device_id

    @property
    def availability(self) -> str:
        return f"{self.prefix}/availability"

    @property
    def bridge_state(self) -> str:
        return f"{self.prefix}/bridge/state"

    def state(self, key: str) -> str:
        return f"{self.prefix}/{key}/state"

    def attributes(self, key: str) -> str:
        return f"{self.prefix}/{key}/attributes"

    def raw(self, kind: str) -> str:
        return f"{self.prefix}/raw/{kind}"

    def config(self, component: str, key: str) -> str:
        return f"{self.discovery_prefix}/{component}/{self.device_id}/{key}/config"


def device_info(device_id: str, name: str) -> Dict[str, Any]:
    return {
        "identifiers": [device_id],
        "name": name,
        "manufacturer": "EBV",
        "model": "Gamma 23 B (via gamma2mqtt)",
        "sw_version": __version__,
    }


def field_config(f: Field, topics: Topics, device: Dict[str, Any], expire_after: int) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "name": f.name,
        "unique_id": f"{topics.device_id}_{f.key}",
        "object_id": f"gamma_{f.key}",
        "state_topic": topics.state(f.key),
        "json_attributes_topic": topics.attributes(f.key),
        "availability_topic": topics.availability,
        "device": device,
    }
    if f.component == "binary_sensor":
        cfg["payload_on"] = "ON"
        cfg["payload_off"] = "OFF"
    else:
        cfg["expire_after"] = expire_after
    if f.unit:
        cfg["unit_of_measurement"] = f.unit
    if f.device_class:
        cfg["device_class"] = f.device_class
    if f.state_class:
        cfg["state_class"] = f.state_class
    if f.icon:
        cfg["icon"] = f.icon
    if f.diagnostic:
        cfg["entity_category"] = "diagnostic"
    if not f.enabled:
        cfg["enabled_by_default"] = False
    for k, v in f.extra.items():
        if v is None:
            cfg.pop(k, None)
        else:
            cfg[k] = v
    return cfg


def bridge_config(key: str, name: str, icon: str, state_class: str, unit: Any,
                  topics: Topics, device: Dict[str, Any]) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "name": name,
        "unique_id": f"{topics.device_id}_bridge_{key}",
        "object_id": f"gamma_{key}",
        "state_topic": topics.bridge_state,
        "value_template": "{{ value_json.%s }}" % key,
        "icon": icon,
        "state_class": state_class,
        "entity_category": "diagnostic",
        "availability_topic": topics.availability,
        "device": device,
    }
    if unit:
        cfg["unit_of_measurement"] = unit
    return cfg


def discovery_messages(topics: Topics, device_name: str, expire_after: int) -> Iterator[Tuple[str, str]]:
    """Yield ``(topic, json_payload)`` for every entity."""
    device = device_info(topics.device_id, device_name)
    for f in FIELDS:
        yield topics.config(f.component, f.key), json.dumps(field_config(f, topics, device, expire_after))
    for key, name, icon, state_class, unit in BRIDGE_FIELDS:
        yield topics.config("sensor", f"bridge_{key}"), json.dumps(
            bridge_config(key, name, icon, state_class, unit, topics, device))
