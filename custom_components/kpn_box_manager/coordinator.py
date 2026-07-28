from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, DOMAIN
from .vendor.kpnboxapi import KPNBoxAPI

PROTOCOLS = {"6": "TCP", "17": "UDP", "6,17": "TCP + UDP"}


class KPNBoxCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        super().__init__(hass, logger=__import__("logging").getLogger(__name__), name=DOMAIN, update_interval=timedelta(minutes=5))
        self.config = config

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.hass.async_add_executor_job(read_all, self.config)
        except Exception as error:
            raise UpdateFailed(f"KPN Box uitlezen mislukt: {error}") from error


def create_client(config: dict[str, Any]) -> KPNBoxAPI:
    api = KPNBoxAPI(host=config[CONF_HOST], timeout=30)
    if not api.login(config[CONF_USERNAME], config[CONF_PASSWORD]):
        api.close()
        raise RuntimeError("Inloggen op de KPN Box is mislukt")
    return api


def read_all(config: dict[str, Any]) -> dict[str, Any]:
    api = create_client(config)
    try:
        leases = [{
            "name": row.get("FriendlyName") or "Onbekend apparaat", "ip": row.get("IPAddress", ""),
            "mac": row.get("MACAddress", ""), "active": bool(row.get("Active")),
            "reserved": bool(row.get("Reserved")), "lease_remaining": row.get("LeaseTimeRemaining"),
        } for row in api.get_dhcp_leases("default")]
        leases.sort(key=lambda row: ip_key(row["ip"]))
        reservations = [{"ip": row.get("IPAddress", ""), "mac": row.get("MACAddress", "")} for row in api.list_ip_reservations("default", False)]
        reservations.sort(key=lambda row: ip_key(row["ip"]))
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
        dhcp = api.get_dhcp_server("default")
        device = api.get_device_info()
        connection = api.get_connection_info()
        return {"leases": leases, "reservations": reservations, "forwards": forwards, "dhcp": dhcp, "device": device, "wan": connection.get("wan_status", {}), "ppp": connection.get("ppp_info", {})}
    finally:
        api.close()


def ip_key(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except (AttributeError, ValueError):
        return (999,)
