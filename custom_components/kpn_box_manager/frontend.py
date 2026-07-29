from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

CARD_URL = "/kpn_box_manager/kpn-box-manager-card.js"
CARD_PATH = Path(__file__).parent / "www" / "kpn-box-manager-card.js"


async def async_register_frontend(hass: HomeAssistant) -> None:
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=True),
    ])
    add_extra_js_url(hass, f"{CARD_URL}?v=0.3.1")
