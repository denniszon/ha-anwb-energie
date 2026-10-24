# ANWB Energie voor Home Assistant

Onofficiële Home Assistant-integratie voor de dynamische uurtarieven van
ANWB Energie: stroom en gas, als all-in prijs
(incl. energiebelasting en btw) en als kale marktprijs.

> Deze integratie is niet gemaakt door of verbonden aan de ANWB. Ze gebruikt de
> publieke, ongedocumenteerde API achter de tarievenpagina van ANWB Energie. Als
> de ANWB die API wijzigt, kan de integratie stoppen met werken.

## Installatie via HACS

1. HACS → menu (⋮) → **Custom repositories**.
2. Repository `https://github.com/denniszon/ha-anwb-energie`, type **Integration**.
3. Zoek **ANWB Energie**, download, en herstart Home Assistant.
4. **Instellingen → Apparaten & diensten → Integratie toevoegen → ANWB Energie**.

Updates verschijnen daarna vanzelf in HACS.

Minimaal Home Assistant 2025.3.

## Entiteiten

| Entiteit | Eenheid | Inhoud |
|---|---|---|
| `sensor.anwb_energie_stroom_all_in` | €/kWh | Stroomprijs van dit uur, all-in |
| `sensor.anwb_energie_stroom_marktprijs` | €/kWh | Stroomprijs van dit uur, marktprijs |
| `sensor.anwb_energie_gas_all_in` | €/m³ | Gasprijs van dit uur, all-in |
| `sensor.anwb_energie_gas_marktprijs` | €/m³ | Gasprijs van dit uur, marktprijs |
| `sensor.anwb_energie_stroom_laagste_vandaag` | €/kWh | Laagste all-in stroomprijs vandaag |
| `sensor.anwb_energie_stroom_gemiddeld_vandaag` | €/kWh | Gemiddelde all-in stroomprijs vandaag |
| `sensor.anwb_energie_stroom_hoogste_vandaag` | €/kWh | Hoogste all-in stroomprijs vandaag |

De vier prijssensoren hebben deze attributen:

| Attribuut | Inhoud |
|---|---|
| `raw_today`, `raw_tomorrow` | Lijst van `{start, end, value}` per uur (zelfde vorm als Nord Pool) |
| `today_min`, `today_avg`, `today_max` | Statistiek van vandaag |
| `next_hour` | Prijs van het volgende uur |
| `tomorrow_valid` | `true` zodra alle prijzen van morgen bekend zijn |
| `price_type` | `all_in` of `market` |

`raw_today` en `raw_tomorrow` worden niet in de database opgeslagen.

### Wanneer worden prijzen opgehaald?

- Elk uur, en de status wisselt precies op het hele uur.
- Stroomprijzen voor morgen worden tussen 13:00 en 15:00 gepubliceerd. Tussen
  13:00 en 16:00 vraagt de integratie elke 10 minuten opnieuw, tot ze binnen zijn.
- Gas gaat per gasdag (06:00 tot 06:00). Een uur zonder gepubliceerde prijs geeft
  `unknown`.

## Grafieken

Installeer [apexcharts-card](https://github.com/RomRider/apexcharts-card) via
HACS (Frontend). Voorbeelden staan in [`examples/`](examples/):

- [`apexcharts-stroom.yaml`](examples/apexcharts-stroom.yaml): staafgrafiek
  vandaag + morgen, met 7 kleuren: blauw bij een negatieve prijs (je krijgt
  geld terug), daarna van goedkoop (groen) tot duur (rood) en een
  "nu"-markering.
- [`apexcharts-gas.yaml`](examples/apexcharts-gas.yaml): hetzelfde voor gas.
- [`dashboard.yaml`](examples/dashboard.yaml): laagst/gemiddeld/hoogst en een
  schakelaar tussen all-in en marktprijs (met een `input_boolean`-helper).

Plak de YAML in een dashboard via **Kaart toevoegen → Handmatig**.

## Gebruik in automatiseringen

Voorbeeld: is het huidige uur een van de drie goedkoopste van vandaag?

```jinja
{% set prices = state_attr('sensor.anwb_energie_stroom_all_in', 'raw_today')
   | map(attribute='value') | sort | list %}
{{ prices | count >= 3
   and states('sensor.anwb_energie_stroom_all_in') | float(99) <= prices[2] }}
```

## Ontwikkeling

```bash
pip install pytest-homeassistant-custom-component ruff
ruff check . && ruff format --check .
pytest tests
```

## Licentie

MIT
