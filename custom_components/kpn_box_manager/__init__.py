from __future__ import annotations

import ipaddress
import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_HOST, CONF_USERNAME, DOMAIN

MAC_RE = re.compile(r"^(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")
PROTOCOLS = {"6": "TCP", "17": "UDP", "6,17": "TCP + UDP"}

ADD_RESERVATION_SCHEMA = vol.Schema({vol.Required("mac_address"): str, vol.Required("ip_address"): str})
DELETE_RESERVATION_SCHEMA = vol.Schema({vol.Required("mac_address"): str})
ADD_FORWARD_SCHEMA = vol.Schema({
    vol.Required("name"): str,
    vol.Required("destination_ip"): str,
    vol.Required("external_port"): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    vol.Required("internal_port"): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    vol.Required("protocol", default="17"): vol.In(PROTOCOLS),
})
DELETE_FORWARD_SCHEMA = vol.Schema({
    vol.Required("rule_id"): str,
    vol.Required("destination_ip"): str,
    vol.Optional("origin", default="webui"): vol.In({"webui", "upnp"}),
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = dict(entry.data)
    if not hass.services.has_service(DOMAIN, "add_reservation"):
        hass.services.async_register(DOMAIN, "add_reservation", _service_handler(hass, "add_reservation"), schema=ADD_RESERVATION_SCHEMA)
        hass.services.async_register(DOMAIN, "delete_reservation", _service_handler(hass, "delete_reservation"), schema=DELETE_RESERVATION_SCHEMA)
        hass.services.async_register(DOMAIN, "add_port_forward", _service_handler(hass, "add_port_forward"), schema=ADD_FORWARD_SCHEMA)
        hass.services.async_register(DOMAIN, "delete_port_forward", _service_handler(hass, "delete_port_forward"), schema=DELETE_FORWARD_SCHEMA)
    await _sync(hass, dict(entry.data))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data[DOMAIN].pop(entry.entry_id, None)
    if not hass.data[DOMAIN]:
        for service in ("add_reservation", "delete_reservation", "add_port_forward", "delete_port_forward"):
            hass.services.async_remove(DOMAIN, service)
    return True


def _service_handler(hass: HomeAssistant, action: str):
    async def handle(call: ServiceCall) -> None:
        entries = hass.data.get(DOMAIN, {})
        if not entries:
            raise HomeAssistantError("KPN Box Manager is niet geconfigureerd")
        config = next(iter(entries.values()))
        try:
            await hass.async_add_executor_job(_mutate, config, action, dict(call.data))
            await _sync(hass, config)
        except HomeAssistantError:
            raise
        except Exception as error:
            raise HomeAssistantError(f"KPN Box-actie mislukt: {error}") from error
    return handle


def _client(config: dict[str, Any]):
    from .vendor.kpnboxapi import KPNBoxAPI
    api = KPNBoxAPI(host=config[CONF_HOST], timeout=30)
    if not api.login(config[CONF_USERNAME], config[CONF_PASSWORD]):
        raise HomeAssistantError("Inloggen op de KPN Box is mislukt")
    return api


def _mutate(config: dict[str, Any], action: str, data: dict[str, Any]) -> None:
    api = _client(config)
    try:
        if action == "add_reservation":
            mac = valid_mac(data["mac_address"])
            ip = valid_ip(data["ip_address"])
            rows = api.list_ip_reservations("default", False)
            conflict = next((row for row in rows if row.get("IPAddress") == ip and row.get("MACAddress", "").lower() != mac), None)
            if conflict:
                raise HomeAssistantError(f"{ip} is al gereserveerd voor {conflict.get('MACAddress')}")
            existing = next((row for row in rows if row.get("MACAddress", "").lower() == mac), None)
            (api.set_static_lease if existing else api.add_static_lease)(mac, ip, "default")
            if not any(row.get("IPAddress") == ip and row.get("MACAddress", "").lower() == mac for row in api.list_ip_reservations("default", False)):
                raise HomeAssistantError("Het modem heeft de reservering niet bevestigd")
        elif action == "delete_reservation":
            mac = valid_mac(data["mac_address"])
            api.delete_static_lease(mac, "default")
            if any(row.get("MACAddress", "").lower() == mac for row in api.list_ip_reservations("default", False)):
                raise HomeAssistantError("Het modem heeft de verwijdering niet bevestigd")
        elif action == "add_port_forward":
            destination = valid_ip(data["destination_ip"])
            external = str(data["external_port"])
            existing = [row for rows in api.get_all_port_forwarding().values() for row in rows]
            if any(str(row.get("ExternalPort")) == external for row in existing):
                raise HomeAssistantError(f"Externe poort {external} bestaat al; verwijder de bestaande regel eerst")
            api.add_port_forwarding_rule(data["name"], str(data["internal_port"]), external, destination, data["protocol"], data["name"], True)
            if not any(str(row.get("ExternalPort")) == external and row.get("DestinationIPAddress") == destination for rows in api.get_all_port_forwarding().values() for row in rows):
                raise HomeAssistantError("Het modem heeft de portforward niet bevestigd")
        elif action == "delete_port_forward":
            destination = valid_ip(data["destination_ip"])
            api.delete_port_forwarding_rule(data["rule_id"], destination, data["origin"])
            if any(row.get("Id") == data["rule_id"] for rows in api.get_all_port_forwarding().values() for row in rows):
                raise HomeAssistantError("Het modem heeft de verwijdering niet bevestigd")
    finally:
        api.close()


async def _sync(hass: HomeAssistant, config: dict[str, Any]) -> None:
    reservations, forwards = await hass.async_add_executor_job(_read_mutable_data, config)
    hass.states.async_set("sensor.kpn_box_dhcp_reserveringen", len(reservations), {
        "friendly_name": "KPN Box DHCP-reserveringen", "icon": "mdi:ip-network", "reservations": reservations,
    })
    enabled = sum(row["enabled"] for row in forwards)
    hass.states.async_set("sensor.kpn_box_port_forwards", len(forwards), {
        "friendly_name": "KPN Box portforwards", "icon": "mdi:router-network", "enabled_count": enabled,
        "disabled_count": len(forwards) - enabled, "rules": forwards,
    })


def _read_mutable_data(config: dict[str, Any]):
    api = _client(config)
    try:
        reservations = [{"ip": row.get("IPAddress", ""), "mac": row.get("MACAddress", "")} for row in api.list_ip_reservations("default", False)]
        reservations.sort(key=lambda row: tuple(int(part) for part in row["ip"].split(".")))
        forwards = []
        for rows in api.get_all_port_forwarding().values():
            for row in rows:
                forwards.append({
                    "id": row.get("Id", ""), "name": row.get("Description") or row.get("Id") or "Naamloos",
                    "origin": row.get("Origin", ""), "protocol": PROTOCOLS.get(str(row.get("Protocol", "")), str(row.get("Protocol", ""))),
                    "external_port": row.get("ExternalPort", ""), "internal_port": row.get("InternalPort", ""),
                    "destination": row.get("DestinationIPAddress", ""), "enabled": bool(row.get("Enable")),
                })
        forwards.sort(key=lambda row: int(row["external_port"]) if str(row["external_port"]).isdigit() else 65536)
        return reservations, forwards
    finally:
        api.close()


def valid_ip(value: str) -> str:
    return str(ipaddress.IPv4Address(value.strip()))


def valid_mac(value: str) -> str:
    normalized = value.strip().lower()
    if not MAC_RE.fullmatch(normalized):
        raise HomeAssistantError("Ongeldig MAC-adres")
    return normalized
