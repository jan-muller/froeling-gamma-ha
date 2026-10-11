import json

from gamma2mqtt.bridge import Bridge, BridgeConfig
from gamma2mqtt.discovery import Topics, discovery_messages
from gamma2mqtt.model import FIELDS

from test_protocol import F1002, F2004_FLAME, F2004_NOFLAME, F2806_10


class FakeMqtt:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, retain))

    def topics(self):
        return [t for t, _, _ in self.published]


def make_bridge(**kw):
    cfg = BridgeConfig(**kw)
    return Bridge(source=None, config=cfg, mqtt_client=FakeMqtt())


def test_discovery_payloads_are_valid_json_and_unique():
    topics = Topics("gamma2mqtt", "homeassistant", "gamma23b")
    msgs = list(discovery_messages(topics, "Gamma", 900))
    assert len(msgs) == len(FIELDS) + 3
    seen = set()
    for topic, payload in msgs:
        cfg = json.loads(payload)
        assert topic.startswith("homeassistant/")
        assert cfg["unique_id"] not in seen
        seen.add(cfg["unique_id"])
        assert cfg["availability_topic"] == "gamma2mqtt/availability"
        assert cfg["device"]["identifiers"] == ["gamma23b"]
    flame = json.loads(dict(msgs)["homeassistant/binary_sensor/gamma23b/flame_request/config"])
    assert flame["payload_on"] == "ON" and "expire_after" not in flame
    assert "device_class" not in flame


def test_publishes_only_on_change_and_marks_online():
    b = make_bridge()
    b.handle_bytes(F2004_NOFLAME)
    assert ("gamma2mqtt/flame_request/state", "OFF", True) in b.client.published
    assert ("gamma2mqtt/boiler_temperature/state", "73", True) in b.client.published
    assert ("gamma2mqtt/availability", "online", True) in b.client.published
    n = len(b.client.published)
    b.handle_bytes(F2004_NOFLAME)  # identical -> nothing new
    assert len(b.client.published) == n
    b.handle_bytes(F2004_FLAME)
    assert ("gamma2mqtt/flame_request/state", "ON", True) in b.client.published[n:]
    assert ("gamma2mqtt/outside_temperature/state", "12.5", True) in b.client.published[n:]


def test_attributes_carry_confidence():
    b = make_bridge()
    b.handle_bytes(F1002 + F2806_10)
    attrs = {t: json.loads(p) for t, p, _ in b.client.published if t.endswith("/attributes")}
    assert attrs["gamma2mqtt/heating_flow_temperature/attributes"]["confidence"] == "probable"
    assert attrs["gamma2mqtt/heating_flow_temperature/attributes"]["position"] == "P11"
    assert attrs["gamma2mqtt/room_temperature/attributes"]["source"] == "10"


def test_goes_offline_when_stale(monkeypatch):
    b = make_bridge(stale_timeout=5)
    b.handle_bytes(F2004_NOFLAME)
    assert b.online is True
    b.last_frame_at -= 10
    b._periodic()
    assert b.online is False
    assert b.client.published[-2:][0][0] in ("gamma2mqtt/availability", "gamma2mqtt/bridge/state")
    assert ("gamma2mqtt/availability", "offline", True) in b.client.published


def test_raw_topic_optional():
    b = make_bridge(publish_raw=True)
    b.handle_bytes(F1002)
    assert any(t == "gamma2mqtt/raw/1002" for t in b.client.topics())
