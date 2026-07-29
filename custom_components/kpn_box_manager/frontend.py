from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant

CARD_URL = "/kpn_box_manager/kpn-box-manager-card.js"
CARD_RESOURCE_URL = f"{CARD_URL}?v=0.3.3"
CARD_PATH = Path(__file__).parent / "www" / "kpn-box-manager-card.js"


async def async_register_frontend(hass: HomeAssistant) -> None:
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=True),
    ])
    resources = hass.data["lovelace"].resources
    if not resources:
        return
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    existing = next((item for item in resources.async_items() if item["url"].startswith(CARD_URL)), None)
    payload = {"res_type": "module", "url": CARD_RESOURCE_URL}
    if existing and existing["url"] != CARD_RESOURCE_URL and isinstance(resources, ResourceStorageCollection):
        await resources.async_update_item(existing["id"], payload)
    elif not existing and getattr(resources, "async_create_item", None):
        await resources.async_create_item(payload)
