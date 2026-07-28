from __future__ import annotations

from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KPNBoxCoordinator


def count_active(data): return sum(row["active"] for row in data["leases"])
def count_reserved(data): return sum(row["reserved"] for row in data["leases"])

DESCRIPTIONS = (
    ("dhcp_adressen", "DHCP-adressen", "mdi:router-network", lambda d: len(d["leases"]), lambda d: {"active_count": count_active(d), "inactive_count": len(d["leases"]) - count_active(d), "reserved_count": count_reserved(d), "addresses": d["leases"]}, None),
    ("dhcp_actief", "DHCP actief", "mdi:lan-connect", count_active, lambda d: {}, None),
    ("dhcp_inactief", "DHCP inactief", "mdi:lan-disconnect", lambda d: len(d["leases"]) - count_active(d), lambda d: {}, None),
    ("dhcp_gereserveerd", "DHCP gereserveerd", "mdi:pin", count_reserved, lambda d: {}, None),
    ("port_forwards", "Portforwards", "mdi:router-network", lambda d: len(d["forwards"]), lambda d: {"enabled_count": sum(x["enabled"] for x in d["forwards"]), "disabled_count": sum(not x["enabled"] for x in d["forwards"]), "rules": d["forwards"]}, None),
    ("dhcp_reserveringen", "DHCP-reserveringen", "mdi:ip-network", lambda d: len(d["reservations"]), lambda d: {"reservations": d["reservations"]}, None),
    ("dhcp_config", "DHCP-configuratie", "mdi:server-network", lambda d: "aan" if d["dhcp"].get("Enable") else "uit", lambda d: {"authoritative": bool(d["dhcp"].get("Authoritative")), "minimum": d["dhcp"].get("MinAddress"), "maximum": d["dhcp"].get("MaxAddress"), "subnet_mask": d["dhcp"].get("SubnetMask"), "gateway": d["dhcp"].get("IPRouters"), "dns_servers": d["dhcp"].get("DNSServers"), "lease_time": d["dhcp"].get("LeaseTime"), "active_leases": d["dhcp"].get("LeaseNumberOfEntries")}, EntityCategory.DIAGNOSTIC),
    ("internet", "Internet", "mdi:web", lambda d: d["wan"].get("ConnectionState", "Onbekend"), lambda d: {"link_type": d["wan"].get("LinkType"), "link_state": d["wan"].get("LinkState"), "protocol": d["wan"].get("Protocol"), "public_ipv4": d["wan"].get("IPAddress") or d["device"].get("ExternalIPAddress"), "ipv6": d["wan"].get("IPv6Address"), "gateway": d["wan"].get("RemoteGateway"), "dns_servers": d["wan"].get("DNSServers"), "last_error": d["wan"].get("LastConnectionError"), "transport": d["ppp"].get("TransportType"), "mru": d["ppp"].get("MaxMRUSize")}, EntityCategory.DIAGNOSTIC),
    ("router_info", "Routerinformatie", "mdi:router-wireless", lambda d: d["device"].get("DeviceStatus", "Onbekend"), lambda d: {"manufacturer": d["device"].get("Manufacturer"), "model": d["device"].get("ModelName"), "serial_number": d["device"].get("SerialNumber"), "base_mac": d["device"].get("BaseMAC"), "hardware_version": d["device"].get("HardwareVersion"), "software_version": d["device"].get("SoftwareVersion"), "rescue_version": d["device"].get("RescueVersion"), "uptime_seconds": d["device"].get("UpTime"), "reboots": d["device"].get("NumberOfReboots")}, EntityCategory.DIAGNOSTIC),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(KPNBoxSensor(coordinator, entry, *description) for description in DESCRIPTIONS)


class KPNBoxSensor(CoordinatorEntity[KPNBoxCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str, name: str, icon: str, value_fn: Callable, attrs_fn: Callable, category) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_entity_category = category
        self._value_fn = value_fn
        self._attrs_fn = attrs_fn
        device = coordinator.data["device"]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.unique_id)}, name="KPN Box", manufacturer=device.get("Manufacturer"), model=device.get("ModelName"), sw_version=device.get("SoftwareVersion"), hw_version=device.get("HardwareVersion"), serial_number=device.get("SerialNumber"))

    @property
    def native_value(self) -> Any:
        return self._value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._attrs_fn(self.coordinator.data)
