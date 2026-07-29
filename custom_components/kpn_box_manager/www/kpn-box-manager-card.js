(() => {
  const TAG = "kpn-box-manager-card";
  if (customElements.get(TAG)) {
    console.info(`${TAG}: already registered; keeping existing implementation`);
    return;
  }

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

  class KPNBoxManagerCard extends HTMLElement {
    setConfig(config) {
      this.config = { title: "KPN Box beheer", section: "both", ...config };
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      this.render();
    }

    set hass(hass) {
      const previous = this._hass;
      this._hass = hass;
      const keys = ["sensor.kpn_box_dhcp_reserveringen", "sensor.kpn_box_portforwards"];
      if (!previous || keys.some((key) => previous.states[key]?.last_updated !== hass.states[key]?.last_updated)) this.render();
    }

    getCardSize() { return 8; }

    render() {
      if (!this.shadowRoot || !this.config || !this._hass) return;
      const reservationState = this._hass.states["sensor.kpn_box_dhcp_reserveringen"];
      const forwardState = this._hass.states["sensor.kpn_box_portforwards"];
      const reservations = reservationState?.attributes?.reservations || [];
      const forwards = forwardState?.attributes?.rules || [];
      const showReservations = ["both", "reservations"].includes(this.config.section);
      const showForwards = ["both", "forwards"].includes(this.config.section);

      this.shadowRoot.innerHTML = `
        <style>
          :host{display:block} ha-card{padding:16px} h2{margin:0 0 14px;font-size:20px} h3{margin:18px 0 8px;font-size:16px}
          form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:14px} label{font-size:12px;color:var(--secondary-text-color)}
          input,select{box-sizing:border-box;width:100%;margin-top:4px;padding:10px;border:1px solid var(--divider-color);border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit}
          button{padding:10px 14px;border:0;border-radius:8px;background:var(--primary-color);color:var(--text-primary-color);cursor:pointer;font-weight:600}
          button.danger{background:var(--error-color)} button.small{padding:6px 9px;font-size:12px}.full{grid-column:1/-1}
          .rows{display:grid;gap:7px}.row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px;border-radius:8px;background:var(--secondary-background-color)}
          .meta{font-size:12px;color:var(--secondary-text-color);margin-top:2px}.right{display:flex;align-items:center;gap:8px}.status{min-height:20px;font-size:13px}.ok{color:var(--success-color)}.error{color:var(--error-color)}
          @media(max-width:600px){form{grid-template-columns:1fr}.full{grid-column:auto}.row{align-items:flex-start}.right{flex-direction:column;align-items:flex-end}}
        </style>
        <ha-card>
          <h2>${esc(this.config.title)}</h2>
          <div id="status" class="status"></div>
          ${showReservations ? `
            <section><h3>DHCP-reservering toevoegen of verplaatsen</h3>
              <form id="reservation-form">
                <label>MAC-adres<input name="mac" required placeholder="aa:bb:cc:dd:ee:ff"></label>
                <label>IP-adres<input name="ip" required placeholder="192.168.2.100" inputmode="decimal"></label>
                <button class="full" type="submit">Reservering opslaan</button>
              </form>
              <div class="rows">${reservations.map((row) => `<div class="row"><div><strong>${esc(row.ip)}</strong><div class="meta">${esc(row.mac)}</div></div><button class="danger small delete-reservation" data-mac="${esc(row.mac)}">Verwijder</button></div>`).join("") || "Geen reserveringen"}</div>
            </section>` : ""}
          ${showForwards ? `
            <section><h3>Portforward toevoegen</h3>
              <form id="forward-form">
                <label>Naam<input name="name" required></label><label>Doel-IP<input name="destination" required inputmode="decimal"></label>
                <label>Externe poort<input name="external" required type="number" min="1" max="65535"></label><label>Interne poort<input name="internal" required type="number" min="1" max="65535"></label>
                <label>Protocol<select name="protocol"><option value="17">UDP</option><option value="6">TCP</option><option value="6,17">TCP + UDP</option></select></label>
                <button type="submit">Portforward opslaan</button>
              </form>
              <div class="rows">${forwards.map((row) => `<div class="row"><div><strong>${esc(row.name)}</strong><div class="meta">${esc(row.protocol)} · :${esc(row.external_port)} → ${esc(row.destination)}:${esc(row.internal_port)}</div></div><div class="right"><span>${row.enabled ? "Actief" : "Uit"}</span><button class="danger small delete-forward" data-id="${esc(row.id)}" data-destination="${esc(row.destination)}" data-origin="${esc(row.origin)}">Verwijder</button></div></div>`).join("") || "Geen portforwards"}</div>
            </section>` : ""}
        </ha-card>`;

      this.bindEvents();
    }

    bindEvents() {
      this.shadowRoot.querySelector("#reservation-form")?.addEventListener("submit", async (event) => {
        event.preventDefault(); const data = new FormData(event.currentTarget);
        await this.call("add_reservation", { mac_address: data.get("mac"), ip_address: data.get("ip") }, "Reservering opgeslagen");
      });
      this.shadowRoot.querySelector("#forward-form")?.addEventListener("submit", async (event) => {
        event.preventDefault(); const data = new FormData(event.currentTarget);
        await this.call("add_port_forward", { name:data.get("name"), destination_ip:data.get("destination"), external_port:Number(data.get("external")), internal_port:Number(data.get("internal")), protocol:data.get("protocol") }, "Portforward opgeslagen");
      });
      this.shadowRoot.querySelectorAll(".delete-reservation").forEach((button) => button.addEventListener("click", async () => {
        if (confirm(`Reservering voor ${button.dataset.mac} verwijderen?`)) await this.call("delete_reservation", { mac_address:button.dataset.mac }, "Reservering verwijderd");
      }));
      this.shadowRoot.querySelectorAll(".delete-forward").forEach((button) => button.addEventListener("click", async () => {
        if (confirm(`Portforward ${button.dataset.id} verwijderen?`)) await this.call("delete_port_forward", { rule_id:button.dataset.id, destination_ip:button.dataset.destination, origin:button.dataset.origin }, "Portforward verwijderd");
      }));
    }

    async call(service, data, success) {
      const status = this.shadowRoot.querySelector("#status");
      status.className = "status"; status.textContent = "Bezig…";
      try {
        await this._hass.callService("kpn_box_manager", service, data);
        status.className = "status ok"; status.textContent = success;
      } catch (error) {
        status.className = "status error"; status.textContent = error?.message || String(error);
      }
    }

    static getStubConfig() { return { title: "KPN Box beheer", section: "both" }; }
  }

  customElements.define(TAG, KPNBoxManagerCard);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === TAG)) window.customCards.push({ type: TAG, name: "KPN Box Manager", description: "Beheer DHCP-reserveringen en portforwards", preview: true });
  console.info("%c KPN Box Manager Card 0.3.2 ", "color:white;background:#186faf;font-weight:bold");
})();
