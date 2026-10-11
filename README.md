# froeling-gamma-ha

Fröling FH-G Turbo 2000 houtketel + EBV Gamma 23 B regelaar → Home Assistant, lokaal en zonder cloud.

| Map | Wat |
|---|---|
| [`gamma2mqtt/`](gamma2mqtt) | Python-service op de Raspberry Pi: leest de Gamma passief via RS485 (9600 8S1), valideert CRC-16/KERMIT, decodeert bekende velden en publiceert via MQTT Discovery. |
| [`froeling-gamma-card/`](froeling-gamma-card) | Lovelace-kaart (HACS) met een schematische weergave van ketel, buffer, boiler en cv-circuit met de live waarden op hun plek. |
| [`GAMMA_23B_COMPLEET_CLAUDE_PAKKET/`](GAMMA_23B_COMPLEET_CLAUDE_PAKKET) | Technische overdracht, captures (CSV) en de oorspronkelijke discovery-scripts. **Leidend protocoldocument:** `GAMMA_23B_HOME_ASSISTANT_HANDOFF.md`. |

Dataflow: `Gamma 23 B ──RS485──> Pi (gamma2mqtt) ──MQTT──> Home Assistant ──> froeling-gamma-card`

Veiligheid: er wordt uitsluitend gelezen. Geen RS485-writes, geen ketelsturing op basis van
voorlopig geïnterpreteerde statusbytes. De aansteekvraag (`2004 P19`) is een kandidaat totdat een
live overgang van het displayvlammetje is gelogd.
