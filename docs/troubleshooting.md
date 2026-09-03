# Wat er stukging, en waarom

Dit is de uitgebreide versie van het "Bekende valkuilen"-stuk in de README.
De meeste problemen zaten niet in de dashboardcode maar in de **verouderde
community-component** voor dit scherm. Als je zelf een LilyGo T5 4.7" met een
moderne ESPHome aan de praat probeert te krijgen, is dit waarschijnlijk het
nuttigste bestand in deze repo.

Getest op **ESPHome 2026.8.1** met **ESP-IDF 5.5.5**, Arduino-framework,
op een ESP32-WROVER-E rev 3.0 met 8 MB PSRAM en 4 MB flash.

---

## 1. Waarom de component lokaal staat en niet als git-source

De bekende fork `github://vbaksa/esphome` (component `lilygo_t5_47_display`)
compileert niet meer op moderne ESPHome. Daarom staat er een **gepatchte
kopie** in `esphome/components/lilygo_t5_47_display/`, ingeladen via:

```yaml
external_components:
  - source:
      type: local
      path: components
    components: [lilygo_t5_47_display]
```

Zet je dit terug naar de git-source, dan ben je alle onderstaande fixes kwijt.

---

## 2. De vijf compile-fouten

### 2.1 Dubbele componentregistratie
`display.py` riep zowel `cg.register_component()` als
`display.register_display()` aan. `register_display` doet dat al. Resultaat:
validatiefout. De extra aanroep is verwijderd.

### 2.2 `display.DisplayBufferRef` bestaat niet meer

```
AttributeError: module 'esphome.components.display' has no attribute 'DisplayBufferRef'
```

Moderne ESPHome definieert in `esphome/components/display/__init__.py`:

```python
DisplayRef = Display.operator("ref")
```

Dus `display.DisplayBufferRef` → `display.DisplayRef`.

### 2.3 `epd_driver.h: No such file or directory`

Twee losse oorzaken die op elkaar lijken:

**a) Verkeerd `lib_deps`-formaat.** De originele regel was

```python
cg.add_library("https://github.com/vroland/epdiy.git", None)
```

In `esphome/core/__init__.py` bouwt `Library.as_lib_dep` de PlatformIO-entry
op. Met de URL als *naam* en `repository=None` krijg je een kale URL, en die
wordt onder de huidige ESP-IDF-build niet betrouwbaar geresolved. Correct is
`name=repository`:

```python
cg.add_library("epdiy", None, "https://github.com/vroland/epdiy.git")
```

**b) De header bestaat simpelweg niet meer.** In de huidige epdiy heet de
publieke header `epdiy.h`; die include't zelf `epd_highlevel.h`,
`epd_board.h`, `epd_display.h` enzovoort. In `LilygoT547Display.h` zijn de
twee losse includes vervangen door één `#include "epdiy.h"`.

### 2.4 `epd_init()` heeft een nieuwe signatuur

Was:

```cpp
epd_init(EPD_OPTIONS_DEFAULT);
```

Is nu:

```cpp
void epd_init(const EpdBoardDefinition* board, const EpdDisplay_t* display,
              enum EpdInitOptions options);
```

Voor dit bord:

```cpp
epd_init(&epd_board_lilygo_t5_47, &ED047TC1, EPD_OPTIONS_DEFAULT);
```

Twee dingen om op te letten:

* **`ED047TC1`, niet `ED097TC2`.** Het voorbeeld `examples/lilygo-t5-47-epd-platformio`
  in de epdiy-repo gebruikt `ED097TC2`, maar dat is het 9,7"-paneel
  (1200x825). `ED047TC1` is 960x540 en dus de juiste voor de T5 4.7".
* **`epd_set_vcom()` is niet nodig.** In `epd_board_lilygo_t5_47` is
  `set_vcom` gewoon `NULL`; VCOM ligt op dit bord in hardware vast.

### 2.5 Dubbelzinnige basisklasse

```
error: 'esphome::PollingComponent' is an ambiguous base of 'LilygoT547Display'
```

De klasse erfde van `PollingComponent` én `display::DisplayBuffer`, maar
`DisplayBuffer → Display → PollingComponent`. `PollingComponent` zat er dus
dubbel in. Opgelost door alleen van `display::DisplayBuffer` te erven.

---

## 3. De twee runtime-fouten (compileren prima, werken niet)

### 3.1 Boot loop: PSRAM staat uit

```
assert failed: epd_hl_init highlevel.c:44 (state.back_fb != NULL)
```

epdiy alloceert de framebuffers met

```c
state.back_fb = heap_caps_aligned_alloc(16, fb_size, MALLOC_CAP_SPIRAM);
assert(state.back_fb != NULL);
```

dus **PSRAM moet aan staan**. De oude firmware regelde dat met de
Arduino-vlag `-DBOARD_HAS_PSRAM`, maar ESPHome bouwt tegenwoordig via ESP-IDF
en daar heeft die vlag geen effect. Toevoegen aan de YAML:

```yaml
psram:
  mode: quad
  speed: 80MHZ
```

Controle in de log: `PSRAM: Available: YES, Size: 8192 kB`.

> **Je bricked je apparaat hier niet mee.** ESPHome's safe mode slaat na 10
> mislukte boots aan en houdt WiFi + OTA 300 seconden in de lucht. Je kunt er
> gewoon een nieuwe build overheen flashen.

### 3.2 Leeg scherm: de kleuren stonden omgekeerd

Dit was de lastigste. Symptoom: het scherm flitst één keer (de wisser) en
blijft daarna leeg, terwijl de logs zeggen dat er getekend is.

epdiy's conventie is **255 = wit, 0 = zwart**. Bewijs: `epd_hl_set_all_white`
doet `memset(fb, 0xFF, ...)`, en `epd_draw_pixel` schrijft de nibble
rechtstreeks in de framebuffer.

De upstream `draw_absolute_pixel_internal` deed precies het omgekeerde: wit
werd `0`, zwart werd `255 - luminantie`. Gevolg:

1. zwarte tekst werd als **wit** weggeschreven, dus onzichtbaar; en
2. `epd_hl_update_screen` vergelijkt de front- met de back-framebuffer, zag
   **geen enkel verschil**, en stuurde dus helemaal niets naar het paneel.

De fix is simpelweg de luminantie rechtstreeks doorgeven:

```cpp
int lum = (0.2126 * color.red) + (0.7152 * color.green) + (0.0722 * color.blue);
epd_draw_pixel(x, y, (uint8_t) lum, fb);
```

> **Snelste sanity-check:** een geslaagde tekening duurt ~3,3-3,8 seconden.
> ESPHome logt dan `a scheduled task took a long time for an operation
> (3756 ms)`. Een *mislukte* tekening is in milliseconden klaar, want er valt
> niets te sturen. Die looptijd zegt je in één oogopslag of het écht werkte.

---

## 4. Overige verbeteringen in de component

* **`clear()` deed een hardware-wispuls.** ESPHome roept `Display::clear()`
  (virtueel!) aan vanuit `do_update_()` bij elke redraw zolang `auto_clear`
  aanstaat. Daar wordt alleen een *buffer*-reset verwacht. De upstream-code
  deed daar `epd_fullclear()`, wat elke refresh een volledige witflits gaf.
  Nu: `clear()` = `epd_hl_set_all_white()`, en de hardware-wis zit in een
  aparte `full_clear()` die één keer per boot draait via `clear: true`.
  * `clear: true` is bewust aan: na elke deep-sleep-wake denkt epdiy dat het
    scherm wit is, terwijl er nog het vorige beeld staat. Zonder die wis
    krijg je ghosting.
* **`temperature_` was als `bool` gedeclareerd**, dus `set_temperature(23)`
  werd stilletjes `1`. Nu `uint32_t`. Voor dit paneel maakt het overigens
  niets uit: `epdiy_ED047TC1` heeft `num_temp_ranges = 1`, dus de
  waveform-keuze hangt niet van de temperatuur af.
* De foutcode van `epd_hl_update_screen` werd stil weggegooid en wordt nu
  gelogd.
* Een korte `delay()` vóór `epd_poweroff()` zodat het beeld kan uitharden.

---

## 5. Leesbaarheid op e-paper

Twee lessen die je bij elke layout-wijziging weer nodig hebt.

### 5.1 Arcering werkt niet, gebruik echte grijstinten

De eerste versie tekende de balken met 1 pixel dunne zwarte streepjes met 2
tot 7 pixels ertussen: nagebootst grijs, omdat de kapotte driver geen grijs
kon. Op het echte scherm was dat vrijwel onleesbaar; bij de goedkoopste uren
is dat ongeveer 14% inktdekking.

Nu de kleurconversie klopt zijn de **16 echte grijswaarden** van het paneel
beschikbaar. Massieve vlakken dus:

```cpp
int g = (int) (200.0f - norm * 140.0f);   // goedkoop 200 (licht) .. duur 60 (donker)
it.filled_rectangle(bar_x, top_y, bar_w, h, Color(g, g, g));
it.rectangle(bar_x, top_y, bar_w, h, black);
```

Daarbij ook: hulplijnen van zwarte stippels naar `Color(180,180,180)` (die
concurreerden met de balken), en de gemiddelde-stippellijn wordt **ná** de
balken getekend zodat hij er bovenop ligt.

### 5.2 Dunne stokken worden niet vol zwart: verzwaar het font

Kleine tekst kwam grijzig over. Het is **geen** anti-aliasing: ESPHome-fonts
hebben `bpp` default 1, dus glyphs zijn puur zwart/wit. Het is fysiek: bij een
GC16-refresh krijgt een geïsoleerde 1 pixel brede lijn te weinig aandrijving.

Het bewijs stond op het scherm zelf: "Laagste:" en "Hoogste:" (`Roboto@700`,
21 px) waren kraakhelder, terwijl "Gemiddeld:" (`Roboto` regular, **dezelfde**
21 px) er duidelijk lichter uitzag. Dezelfde grijzigheid zie je in de 1 pixel
brede randjes om de balken.

De oplossing is dus **zwaarder gewicht**, niet een grotere maat en zeker niet
"meer contrast" (het is al zuiver zwart). Alle fonts in deze config staan op
`@700`. Ruimte is geen bezwaar: flash zit op ~56%, RAM op ~28%.

### 5.3 Layout-correcties uit dezelfde ronde

* Grafiek van 860 naar **830 px** breed. Het "gem"-label stond op x=928 en
  liep het 960 px brede paneel uit.
* De onderste regel van y=505 naar **y=496**. Op 505 valt hij deels achter de
  behuizing.

---

## 6. OTA terwijl het apparaat in deep sleep zit

Standaard sliep dit ontwerp ~7 seconden na het wakker worden alweer in. Elke
OTA was daarmee een gok.

**Belangrijk detail:** `deep_sleep.enter` roept intern `begin_sleep(true)` aan
en negeert daarmee `deep_sleep.prevent`. Een `prevent`-actie alleen is dus
**niet** genoeg. Zie `deep_sleep_component.cpp`:

```cpp
void DeepSleepComponent::begin_sleep(bool manual) {
  if (this->prevent_ && !manual) { ... return; }
```

Opgelost met een eigen vlag:

```yaml
globals:
  - id: stay_awake
    type: bool
    restore_value: no
    initial_value: 'false'
```

en in het `enter_sleep`-script, vóór `deep_sleep.enter`:

```yaml
      - delay: 10s
      - wait_until:
          condition:
            lambda: 'return !id(stay_awake);'
```

`stay_awake` wordt op `true` gezet door `ota: ... on_begin:` (zodat een lopende
upload nooit onderbroken wordt) en door **knop 2 (GPIO34)** als handmatige
onderhoudsknop. Kosten: ongeveer 20 seconden extra wakker per dag.

**In de praktijk:** slaapt hij, druk dan op de wakeup-knop (GPIO39, bovenste
zijknop) zodra de ESPHome-log `Connecting to <ip> port 3232` toont. De
OTA-client doet 3 pogingen met 5 seconden ertussen.

---

## 7. Meerdere wake-knoppen: ext1 `ALL_LOW` doet niet wat je denkt

Toen de vandaag/morgen-toggle erbij kwam, lag het voor de hand om de vrije
knop op GPIO35 als tweede wake-pin toe te voegen. Dat werkt niet.

De originele ESP32 kent voor ext1 maar twee modi: `ALL_LOW` en `ANY_HIGH`. De
knoppen op dit bord zijn active-low, dus `ANY_HIGH` valt af. En `ALL_LOW`
betekent letterlijk: wek als **alle** opgegeven pinnen tegelijk laag zijn. Met
GPIO39 en GPIO35 samen in één ext1-config zou je dus beide knoppen tegelijk
moeten indrukken om het apparaat te wekken.

(ESPHome bevestigt dit ook in `components/deep_sleep/__init__.py`: `ALL_LOW`
wordt daar expliciet beperkt tot `VARIANT_ESP32`.)

### Kijk niet naar EXT1, maar naar "niet-TIMER"

De eerste versie zette de toggle op de wake-pin en testte op
`ESP_SLEEP_WAKEUP_EXT1`. In de praktijk bleek dat de verkeerde aanname: de
knoppen staan in de volgorde **IO39 - IO34 - IO35 - IO0 - RST**, en de knop die
je intuïtief pakt is RST. Een reset is geen EXT1-wake, dus er gebeurde niets.

Beter is het om het om te draaien. Alleen een timer-wake is "de klok"; al het
andere - de wake-pin (EXT1), de resetknop (UNDEFINED), een herstart na OTA -
is een menselijke actie:

```cpp
esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
if (cause == ESP_SLEEP_WAKEUP_TIMER) {
  auto t = id(ha_time).now();               // de klok -> standaardweergave
  if (t.is_valid()) id(show_tomorrow) = (t.hour >= 22);
} else {
  id(show_tomorrow) = !id(show_tomorrow);   // een mens -> omschakelen
}
```

Zo maakt het niet uit welke knop iemand pakt. De wake-oorzaak is in lambdas
gewoon beschikbaar, want `deep_sleep_component.h` include't `<esp_sleep.h>`.

Twee details die makkelijk misgaan:

* Doe dit **niet** in `on_boot` met een hoge prioriteit: `ha_time` is dan nog
  niet gesynchroniseerd en globals met `restore_value` zijn misschien nog niet
  hersteld. Het gebeurt hier in het script dat draait zodra de sensordata
  binnen is.
* Zet er een `view_decided`-vlag omheen. Het script kan per boot meerdere keren
  afgaan, en dan zou je twee keer omschakelen.

---

## 8. Home Assistant: de dubbele `template:`-sleutel

Niet ESPHome-gerelateerd, maar wel een uur zoekwerk waard. Had je al een
`template:`-blok in `configuration.yaml` en voeg je er een tweede toe (voor de
`!include`), dan overschrijft YAML de ene sleutel stilzwijgend met de andere.
Geen foutmelding, "Controleer configuratie" blijft groen, maar je sensor
verschijnt nooit. Zet alles onder **één** `template:`-sleutel.

---

## 9. Van Nord Pool naar Zonneplan: niet zelf omrekenen

Toen de leverancier Zonneplan werd, was de eerste ingeving om de Nord
Pool-spotprijs op te hogen met een formule: `spot + inkoopvergoeding +
energiebelasting + btw`. Doe dat niet. De opslag is een contractvoorwaarde die
kan wijzigen, en de **energiebelasting verandert elk jaar per 1 januari**. Een
handgemaakte formule gaat daardoor stilzwijgend driften: er gaat niets stuk, de
getallen kloppen alleen op een dag net niet meer. Neem de prijs af van de partij
die hem ook factureert.

De architectuur hoefde daar niet voor op de schop. Het CSV-contract naar het
scherm (`0.345,0.337,...` plus attribuut `datum`) bleef identiek; alleen de bron
*binnen* de twee template-sensoren veranderde. **De tekenlogica in de firmware
is geen letter gewijzigd** — op de toevoeging van de gasprijs na, en die stond
los van deze migratie.

Wat je moet weten over het `forecast`-attribuut van
`sensor.zonneplan_current_quarter_hourly_electricity_tariff`:

```json
{"start_date": "2026-09-02T13:00:00+02:00",
 "end_date":   "2026-09-02T13:15:00+02:00",
 "price_tax_included": {"amount": 2536993},
 "price_tax_excluded": {"amount": 1428512},
 "sustainability_score": {"permille": 1000}}
```

* **`amount` staat in 1e-7 EUR.** `2536993` is `0,2536993` EUR/kWh. Delen door
  `10000000`.
* **`price_tax_included` is de all-in consumentenprijs.** Het verschil met
  `price_tax_excluded` is over de hele forecast een *constante* (hier
  `0,1108481`), en dat is precies de energiebelasting inclusief btw. Was de btw
  pas in de laatste stap toegevoegd, dan zou dat verschil proportioneel zijn
  geweest in plaats van constant. Handige controle als je twijfelt of je het
  juiste veld te pakken hebt.
* **Het venster is ruwweg een dag terug tot twee dagen vooruit** (~236
  kwartieren). Vandaag én morgen zitten er dus altijd in; er is geen apart
  ophaalmoment meer nodig zoals bij een day-ahead-fetch.
* De prijzen worden zichtbaar ~2 tot 3x hoger dan kale spot. De grafiek schaalt
  op min/max, dus daar hoefde niets aan.

Groeperen per lokaal uur kan met een tussenstap die de filter-syntax van Jinja
weer bruikbaar maakt:

```jinja
{% set day = namespace(items=[]) %}
{% for f in fc %}
  {% set d = f.start_date | as_datetime | as_local %}
  {% if d.date() == target %}
    {% set day.items = day.items + [ {'h': d.hour, 'v': f.price_tax_included.amount} ] %}
  {% endif %}
{% endfor %}
...
{% set vals = day.items | selectattr('h','eq',h) | map(attribute='v') | list %}
```

Bouw je die tussenlijst uit **tuples** in plaats van dicts, dan werkt
`selectattr('0', ...)` niet: Jinja's `getattr` valt terug op item-lookup met de
*string* `'0'`, en een tuple kent die sleutel niet. Met dicts werkt de fallback
wel.

### Een trigger-based template sensor na een reload

Trigger-based sensors renderen niet uit zichzelf; na `template.reload` blijven
ze op hun oude (of lege) waarde staan tot een trigger afgaat. Handig om er een
event-trigger bij te zetten:

```yaml
    - trigger: event
      event_type: stroomprijzen_refresh
```

Dan forceer je een verse render vanuit Ontwikkelhulpmiddelen > Gebeurtenissen,
zonder op de volgende tijdtrigger te wachten.

### Glyphs voor € en ³

De gedeelde `glyphs`-anchor moest `€³` erbij voor "€/m³ gas". Vergeet je dat,
dan faalt de build met `Codepoint 0x000020ac not found in font`. Dezelfde
valkuil als eerder met de `/` voor "ct/kWh".
