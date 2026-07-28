# KPN Box Manager for Home Assistant

HACS custom integration voor lokaal beheer van een KPN Box. De benodigde client is ingebed en bevat een compatibiliteitsfix voor Home Assistant 2026.7/Python 3.14.

## Functies

- Configuratie via de Home Assistant UI.
- DHCP-adressen met actieve, inactieve en gereserveerde aantallen.
- DHCP-configuratie: bereik, gateway, DNS en leasetijd.
- DHCP-reserveringen en portforwards.
- Internet-, WAN-, firmware-, hardware- en routerinformatie.
- Automatische lokale synchronisatie iedere vijf minuten.
- Reserveringen toevoegen, verplaatsen en verwijderen.
- Portforwards toevoegen en verwijderen.
- Directe coordinator-refresh na iedere geslaagde wijziging.
- Controle van de werkelijke modemstatus, omdat sommige firmware-antwoorden een onjuiste succeswaarde geven.

Getest met KPN Box 14. Andere modellen kunnen afwijken.

## Installatie via HACS

1. HACS → **Integraties** → menu → **Aangepaste repositories**.
2. Voeg `https://github.com/swartb/kpn-box-manager-ha` toe als categorie **Integratie**.
3. Installeer **KPN Box Manager**.
4. Herstart Home Assistant.
5. Instellingen → Apparaten & diensten → Integratie toevoegen → **KPN Box Manager**.
6. Vul host, gebruikersnaam en modemwachtwoord in.

## Services

- `kpn_box_manager.add_reservation`
- `kpn_box_manager.delete_reservation`
- `kpn_box_manager.add_port_forward`
- `kpn_box_manager.delete_port_forward`

Gebruik de Home Assistant-actie-editor om de velden in te vullen. Verwijderingen en netwerkveranderingen kunnen verbindingen onderbreken.

## Ingebedde client

De map `vendor/kpnboxapi` is gebaseerd op `ssl/KPNBoxAPI` versie 0.1.3 (MIT). De lokale wijziging voegt betrouwbare `close()`-afhandeling toe en voorkomt de fout die op Python 3.14 optrad.
