from __future__ import annotations

import ipaddress
import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .coordinator import KPNBoxCoordinator, create_client
from .frontend import async_register_frontend

PLATFORMS = ["sensor"]
MAC_RE = re.compile(r"^(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")
ADD_RESERVATION_SCHEMA = vol.Schema({vol.Required("mac_address"): str, vol.Required("ip_address"): str})
DELETE_RESERVATION_SCHEMA = vol.Schema({vol.Required("mac_address"): str})
ADD_FORWARD_SCHEMA = vol.Schema({vol.Required("name"): str, vol.Required("destination_ip"): str, vol.Required("external_port"): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)), vol.Required("internal_port"): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)), vol.Required("protocol", default="17"): vol.In({"6", "17", "6,17"})})
DELETE_FORWARD_SCHEMA = vol.Schema({vol.Required("rule_id"): str, vol.Required("destination_ip"): str, vol.Optional("origin", default="webui"): vol.In({"webui", "upnp"})})


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    await async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = KPNBoxCoordinator(hass, dict(entry.data))
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"config": dict(entry.data), "coordinator": coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if not hass.services.has_service(DOMAIN, "add_reservation"):
        hass.services.async_register(DOMAIN, "add_reservation", service_handler(hass, "add_reservation"), schema=ADD_RESERVATION_SCHEMA)
        hass.services.async_register(DOMAIN, "delete_reservation", service_handler(hass, "delete_reservation"), schema=DELETE_RESERVATION_SCHEMA)
        hass.services.async_register(DOMAIN, "add_port_forward", service_handler(hass, "add_port_forward"), schema=ADD_FORWARD_SCHEMA)
        hass.services.async_register(DOMAIN, "delete_port_forward", service_handler(hass, "delete_port_forward"), schema=DELETE_FORWARD_SCHEMA)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.data[DOMAIN].pop(entry.entry_id, None)
    if not hass.data[DOMAIN]:
        for service in ("add_reservation", "delete_reservation", "add_port_forward", "delete_port_forward"):
            hass.services.async_remove(DOMAIN, service)
    return True


def service_handler(hass: HomeAssistant, action: str):
    async def handle(call: ServiceCall) -> None:
        entries = hass.data.get(DOMAIN, {})
        if not entries:
            raise HomeAssistantError("KPN Box Manager is niet geconfigureerd")
        runtime = next(iter(entries.values()))
        try:
            await hass.async_add_executor_job(mutate, runtime["config"], action, dict(call.data))
            await runtime["coordinator"].async_request_refresh()
        except HomeAssistantError:
            raise
        except Exception as error:
            raise HomeAssistantError(f"KPN Box-actie mislukt: {error}") from error
    return handle


def mutate(config: dict[str, Any], action: str, data: dict[str, Any]) -> None:
    api = create_client(config)
    try:
        if action == "add_reservation":
            mac, ip = valid_mac(data["mac_address"]), valid_ip(data["ip_address"])
            rows = api.list_ip_reservations("default", False)
            conflict = next((x for x in rows if x.get("IPAddress") == ip and x.get("MACAddress", "").lower() != mac), None)
            if conflict:
                raise HomeAssistantError(f"{ip} is al gereserveerd voor {conflict.get('MACAddress')}")
            existing = next((x for x in rows if x.get("MACAddress", "").lower() == mac), None)
            (api.set_static_lease if existing else api.add_static_lease)(mac, ip, "default")
            if not any(x.get("IPAddress") == ip and x.get("MACAddress", "").lower() == mac for x in api.list_ip_reservations("default", False)):
                raise HomeAssistantError("Het modem heeft de reservering niet bevestigd")
        elif action == "delete_reservation":
            mac = valid_mac(data["mac_address"])
            api.delete_static_lease(mac, "default")
            if any(x.get("MACAddress", "").lower() == mac for x in api.list_ip_reservations("default", False)):
                raise HomeAssistantError("Het modem heeft de verwijdering niet bevestigd")
        elif action == "add_port_forward":
            destination, external = valid_ip(data["destination_ip"]), str(data["external_port"])
            if any(str(x.get("ExternalPort")) == external for rows in api.get_all_port_forwarding().values() for x in rows):
                raise HomeAssistantError(f"Externe poort {external} bestaat al; verwijder de bestaande regel eerst")
            api.add_port_forwarding_rule(data["name"], str(data["internal_port"]), external, destination, data["protocol"], data["name"], True)
            if not any(str(x.get("ExternalPort")) == external and x.get("DestinationIPAddress") == destination for rows in api.get_all_port_forwarding().values() for x in rows):
                raise HomeAssistantError("Het modem heeft de portforward niet bevestigd")
        elif action == "delete_port_forward":
            destination = valid_ip(data["destination_ip"])
            api.delete_port_forwarding_rule(data["rule_id"], destination, data["origin"])
            if any(x.get("Id") == data["rule_id"] for rows in api.get_all_port_forwarding().values() for x in rows):
                raise HomeAssistantError("Het modem heeft de verwijdering niet bevestigd")
    finally:
        api.close()


def valid_ip(value: str) -> str:
    return str(ipaddress.IPv4Address(value.strip()))


def valid_mac(value: str) -> str:
    value = value.strip().lower()
    if not MAC_RE.fullmatch(value):
        raise HomeAssistantError("Ongeldig MAC-adres")
    return value
