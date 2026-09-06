#!/usr/bin/env python3
"""
Preview v2 van t5_47_stroomprijzen (ESPHome-lambda), nu met ECHTE grijstinten
in plaats van arcering.

Belangrijk: het ED047TC1-paneel doet 16 grijswaarden (4 bit). Deze preview
kwantiseert daarom elke grijswaarde naar (g >> 4) * 17, precies zoals epdiy
dat doet, zodat wat je hier ziet ook echt op het scherm haalbaar is.
"""
from PIL import Image, ImageDraw, ImageFont

W, H = 960, 540
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(FONT_DIR + name, size)


f_title = font(30, bold=True)
f_price_big = font(58, bold=True)
f_price_unit = font(22, bold=True)
f_axis = font(20, bold=True)
f_footer = font(21, bold=True)
f_footer_bold = font(21, bold=True)
f_small = font(16, bold=True)
f_gas = font(40, bold=True)


def q(g):
    """Kwantiseer naar de 16 grijswaarden die het paneel echt kan."""
    g = max(0, min(255, int(g)))
    return ((g >> 4) * 17,) * 3


def draw_text(d, xy, txt, fnt, anchor="la", fill=BLACK):
    d.text(xy, txt, font=fnt, fill=fill, anchor=anchor)


def render(prices, is_today, current_idx, date_str, filename, updated_str="21:03", gas=None, hourly=False):
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    count = len(prices)
    price_min, price_max = min(prices), max(prices)
    idx_min, idx_max = prices.index(price_min), prices.index(price_max)
    avg = sum(prices) / count

    # ---- Header ----
    title = "Stroomprijzen vandaag" if is_today else "Stroomprijzen morgen"
    draw_text(d, (20, 14), title, f_title)
    draw_text(d, (20, 52), date_str, f_footer)
    d.line([(0, 114), (960, 114)], fill=BLACK, width=1)

    if is_today:
        cur = f"{prices[current_idx]*100:.1f}".replace(".", ",")
        draw_text(d, (940, 4), cur, f_price_big, anchor="ra")
        draw_text(d, (940, 84), "ct/kWh nu", f_price_unit, anchor="ra")
    else:
        m = f"{price_min*100:.1f}".replace(".", ",")
        draw_text(d, (940, 4), m, f_price_big, anchor="ra")
        hour = round(idx_min * 24 / count)
        draw_text(d, (940, 84), f"ct goedkoopst om {hour:02d}:00", f_price_unit, anchor="ra")

    # Gasprijs links van de huidige stroomprijs. Alleen bij "vandaag": voor
    # morgen publiceert Zonneplan nog geen gasdagprijs.
    if is_today and gas is not None:
        draw_text(d, (740, 36), f"{gas:.2f}".replace(".", ","), f_gas, anchor="ra")
        draw_text(d, (740, 84), "\u20ac/m\u00b3 gas", f_price_unit, anchor="ra")

    # ---- Grafiek ----
    # chart_w van 860 -> 830 zodat het "gem"-label rechts niet meer afvalt
    chart_x, chart_y, chart_w, chart_h = 60, 130, 830, 260
    baseline_y = chart_y + chart_h

    rng = price_max - price_min
    if rng < 0.001:
        rng = 0.01
    disp_min = min(0, price_min - rng * 0.1)
    disp_max = price_max + rng * 0.18
    if disp_max <= disp_min:
        disp_max = disp_min + 0.01
    disp_range = disp_max - disp_min

    def val_to_y(v):
        return baseline_y - int(((v - disp_min) / disp_range) * chart_h)

    y_max_line, y_avg_line, y_min_line = val_to_y(price_max), val_to_y(avg), val_to_y(price_min)

    # Hulplijnen: lichtgrijs i.p.v. zwarte stippels -> rustiger achter de balken
    gy = chart_y
    while gy <= baseline_y:
        d.line([(chart_x, gy), (chart_x + chart_w, gy)], fill=q(180), width=1)
        gy += chart_h // 4

    draw_text(d, (chart_x - 8, y_max_line), f"{price_max*100:.1f}".replace(".", ","), f_axis, anchor="rm")
    draw_text(d, (chart_x - 8, y_min_line), f"{price_min*100:.1f}".replace(".", ","), f_axis, anchor="rm")

    # ---- Balken: massieve grijsvulling, donkerder = duurder ----
    gap = 3
    bar_w = (chart_w - (count - 1) * gap) // count
    label_step = max(1, count // 8)

    for i in range(count):
        bar_x = chart_x + i * (bar_w + gap)
        top_y = val_to_y(prices[i])
        if baseline_y - top_y < 1:
            top_y = baseline_y - 1

        if is_today and i == current_idx:
            d.rectangle([bar_x, top_y, bar_x + bar_w - 1, baseline_y - 1], fill=BLACK)
        else:
            norm = max(0.0, min(1.0, (prices[i] - price_min) / rng))
            # goedkoop = licht (200), duur = donker (60)
            d.rectangle([bar_x, top_y, bar_x + bar_w - 1, baseline_y - 1],
                        fill=q(200 - norm * 140), outline=BLACK, width=1)

        if i % label_step == 0:
            draw_text(d, (bar_x + bar_w // 2, baseline_y + 6), f"{round(i*24/count):02d}", f_axis, anchor="ma")

    # Gemiddelde-lijn bovenop de balken, zodat hij leesbaar blijft
    gx = chart_x
    while gx < chart_x + chart_w:
        d.line([(gx, y_avg_line), (gx + 5, y_avg_line)], fill=BLACK, width=1)
        gx += 10
    draw_text(d, (chart_x + chart_w + 8, y_avg_line), "gem", f_axis, anchor="lm")

    if is_today:
        cx = chart_x + current_idx * (bar_w + gap) + bar_w // 2
        d.polygon([(cx - 6, chart_y - 14), (cx + 6, chart_y - 14), (cx, chart_y - 2)], fill=BLACK)

    mx = chart_x + idx_min * (bar_w + gap) + bar_w // 2
    min_top_y = val_to_y(price_min)
    d.ellipse([mx - 5, chart_y - 29, mx + 5, chart_y - 19], fill=BLACK)
    if min_top_y - 2 > chart_y - 18:
        d.line([(mx, chart_y - 18), (mx, min_top_y - 2)], fill=BLACK, width=1)

    d.line([(0, baseline_y + 26), (960, baseline_y + 26)], fill=BLACK, width=1)

    # ---- Footer ----
    min_h, max_h = round(idx_min * 24 / count), round(idx_max * 24 / count)
    draw_text(d, (20, baseline_y + 38),
              f"Laagste: {price_min*100:.1f}".replace(".", ",") + f" ct ({min_h:02d}:00)", f_footer_bold)
    draw_text(d, (340, baseline_y + 38),
              f"Gemiddeld: {avg*100:.1f}".replace(".", ",") + " ct", f_footer)
    draw_text(d, (600, baseline_y + 38),
              f"Hoogste: {price_max*100:.1f}".replace(".", ",") + f" ct ({max_h:02d}:00)", f_footer_bold)

    # was y=505 -> viel tegen de onderrand aan; nu 496
    tempo = "elk uur" if hourly else "2x per dag"
    draw_text(d, (20, 496), f"bijgewerkt {updated_str} - {tempo}", f_small)
    draw_text(d, (545, 496), "buitenste: vandaag/morgen    midden: tempo", f_small, anchor="ma")
    draw_text(d, (940, 496), "batterij 4,53V", f_small, anchor="ra")

    img.save(filename)
    print("saved", filename)


# Echte Zonneplan-prijzen (all-in incl. energiebelasting en btw), 03/04-09-2026
today = [0.345, 0.337, 0.319, 0.306, 0.300, 0.306, 0.337, 0.359, 0.349, 0.312,
         0.274, 0.236, 0.196, 0.171, 0.165, 0.169, 0.210, 0.280, 0.348, 0.391,
         0.402, 0.369, 0.347, 0.333]

tomorrow = [0.304, 0.281, 0.271, 0.271, 0.262, 0.263, 0.292, 0.315, 0.316, 0.298,
            0.259, 0.207, 0.189, 0.171, 0.179, 0.180, 0.189, 0.216, 0.285, 0.305,
            0.314, 0.318, 0.312, 0.301]

GAS = 1.67   # EUR/m3, sensor.zonneplan_current_tariff_gas

def render_unknown(filename, updated_str="09:20"):
    """Wat je ziet als je naar morgen wisselt terwijl de day-ahead prijzen nog
    niet gepubliceerd zijn."""
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    draw_text(d, (20, 14), "Stroomprijzen morgen", f_title)
    d.line([(0, 114), (960, 114)], fill=BLACK, width=1)
    draw_text(d, (480, 250), "Prijzen van morgen nog niet bekend", f_title, anchor="ma")
    draw_text(d, (480, 300), "Druk op de linker- of rechterknop om te wisselen", f_footer, anchor="ma")
    draw_text(d, (20, 496), f"bijgewerkt {updated_str}", f_small)
    draw_text(d, (545, 496), "buitenste: vandaag/morgen    midden: tempo", f_small, anchor="ma")
    draw_text(d, (940, 496), "batterij 4,53V", f_small, anchor="ra")
    img.save(filename)
    print("saved", filename)


render(today, True, 14, "03-09-2026", "../docs/preview-vandaag.png", updated_str="14:07", gas=GAS, hourly=True)
render(tomorrow, False, 0, "04-09-2026", "../docs/preview-morgen.png", updated_str="21:37")
render_unknown("../docs/preview-morgen-onbekend.png")
