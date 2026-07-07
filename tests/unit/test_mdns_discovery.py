"""Unit tests for mDNS table discovery (modules/core/mdns_discovery)."""

from modules.core.mdns_discovery import TableDiscovery, service_info_to_table


class FakeServiceInfo:
    """Stub of zeroconf ServiceInfo exposing only what service_info_to_table reads."""

    def __init__(self, properties=None, addresses=None, port=8080):
        self.properties = properties or {}
        self._addresses = addresses if addresses is not None else ["192.168.68.130"]
        self.port = port

    def parsed_addresses(self):
        return self._addresses


class TestServiceInfoToTable:
    def test_basic_conversion(self):
        info = FakeServiceInfo(
            properties={b"id": b"abc-123", b"name": b"Living Room", b"version": b"1.2.3"},
            addresses=["192.168.68.130"],
            port=8080,
        )
        table = service_info_to_table(info)
        assert table == {
            "id": "abc-123",
            "name": "Living Room",
            "url": "http://192.168.68.130:8080",
            "host": "192.168.68.130",
            "port": 8080,
            "version": "1.2.3",
        }

    def test_port_80_omitted_from_url(self):
        info = FakeServiceInfo(properties={b"id": b"abc"}, port=80)
        table = service_info_to_table(info)
        assert table["url"] == "http://192.168.68.130"

    def test_missing_id_returns_none(self):
        info = FakeServiceInfo(properties={b"name": b"No Id"})
        assert service_info_to_table(info) is None

    def test_ipv6_only_returns_none(self):
        info = FakeServiceInfo(properties={b"id": b"abc"}, addresses=["fe80::1"])
        assert service_info_to_table(info) is None

    def test_ipv4_preferred_over_ipv6(self):
        info = FakeServiceInfo(
            properties={b"id": b"abc"},
            addresses=["fe80::1", "192.168.68.130"],
        )
        assert service_info_to_table(info)["host"] == "192.168.68.130"

    def test_empty_name_defaults(self):
        info = FakeServiceInfo(properties={b"id": b"abc", b"name": b""})
        assert service_info_to_table(info)["name"] == "Dune Weaver"

    def test_string_properties_accepted(self):
        # zeroconf usually yields bytes, but tolerate str keys/values
        info = FakeServiceInfo(properties={"id": "abc", "name": "Str Table"})
        table = service_info_to_table(info)
        assert table["id"] == "abc"
        assert table["name"] == "Str Table"


class TestTableDiscovery:
    def test_starts_empty_and_not_running(self):
        discovery = TableDiscovery()
        assert discovery.get_tables() == []
        assert not discovery.is_running

    def test_removed_service_is_evicted(self):
        discovery = TableDiscovery()
        discovery._discovered["svc-name"] = {"id": "abc", "name": "T", "url": "http://x"}

        try:
            from zeroconf import ServiceStateChange
        except ImportError:
            return  # zeroconf not installed; eviction path can't run anyway

        discovery._on_service_state_change(
            None, "_dune-weaver._tcp.local.", "svc-name", ServiceStateChange.Removed
        )
        assert discovery.get_tables() == []

    def test_instance_label_sanitizes(self):
        assert TableDiscovery._instance_label("My.Table!") == "MyTable"
        assert TableDiscovery._instance_label("") == "Dune Weaver"
        assert len(TableDiscovery._instance_label("x" * 100)) == 40
