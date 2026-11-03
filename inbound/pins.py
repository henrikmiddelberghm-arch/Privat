"""Rendert Pinterest-Pins (1000x1500 PNG) aus einer JSON-Liste und schreibt die Pin-Texte als CSV.

  python3 pins.py pins/<slug>/pins.json

pins.json: Liste von Pins, jeder mit
  layout:  "titel" | "liste" | "frage" | "schritte"
  theme:   id aus ../adagent/patterns.json (themes), font: id aus ../adagent/patterns.json (fonts)
  kicker:  kleine Zeile oben (optional)        titel: grosse Zeile(n), Akzentwort mit *Sternchen*
  punkte:  Liste (fuer liste/schritte)         unterzeile: kleine Zeile unten (optional)
  foto:    true = Foto-Hintergrund (Platzhalter oder assets/hook.jpg)
  pin_titel, beschreibung, alt, board, link   -> landen in pins.csv (Pinterest-Bulk-Format)
"""
import csv
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
AD = ROOT.parent / "adagent"
P = json.loads((AD / "patterns.json").read_text())
THEMES = {t["id"]: t for t in P["themes"]}
FONTS = {f["id"]: f for f in P["fonts"]}
CFG = json.loads((ROOT / "config.json").read_text())
W, H, M = 1000, 1500, 90


def hexc(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def font(fs, kind, size):
    return ImageFont.truetype(str(AD / "fonts" / fs[kind]), size)


def words(text):
    """'Fotos *ganz sicher* sammeln' -> [(Fotos, False), (ganz, True), (sicher, True), (sammeln, False)]"""
    out, on = [], False
    for w in text.split():
        start = w.startswith("*")
        end = w.rstrip(".,!?:;").endswith("*")
        acc = on or start
        if start and not end:
            on = True
        if end:
            on = False
        out.append((w.replace("*", ""), acc))
    return out


def wrap(d, toks, f, maxw):
    lines, cur = [], []
    for t in toks:
        test = " ".join(x for x, _ in cur + [t])
        if cur and d.textlength(test, font=f) > maxw:
            lines.append(cur)
            cur = []
        cur.append(t)
    if cur:
        lines.append(cur)
    return lines


def draw_rich(d, y, text, f, col, acc, maxw, upper=False, align="center", lh=1.12):
    toks = [(w.upper() if upper else w, a) for w, a in words(text)]
    for line in wrap(d, toks, f, maxw):
        full = " ".join(w for w, _ in line)
        x = (W - d.textlength(full, font=f)) / 2 if align == "center" else M
        for w, a in line:
            d.text((x, y), w, font=f, fill=acc if a else col)
            x += d.textlength(w + " ", font=f)
        y += f.size * lh
    return y


def fit(d, fs, kind, text, maxw, start, min_size, max_lines):
    size = start
    while size > min_size:
        f = font(fs, kind, size)
        if len(wrap(d, [(w, a) for w, a in words(text)], f, maxw)) <= max_lines:
            return f
        size -= 4
    return font(fs, kind, min_size)


def photo_bg():
    src = AD / "assets" / "hook.jpg"
    if not src.exists():
        cands = sorted((AD / "assets").glob("hook_placeholder_*.jpg"))
        src = cands[0] if cands else None
    if not src:
        return None
    im = Image.open(src).convert("RGB")
    s = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1))
    l, t = (im.width - W) // 2, (im.height - H) // 2
    im = im.crop((l, t, l + W, t + H))
    shade = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.blend(im, shade, 0.45)


def render(pin, out):
    th, fs = THEMES[pin.get("theme", "white_terracotta")], FONTS[pin.get("font", "intertight")]
    bg, fg, muted, acc = (hexc(th[k]) for k in ("bg", "fg", "muted", "accent"))
    up = fs.get("upper", False)
    img = Image.new("RGB", (W, H), bg)
    if pin.get("foto"):
        ph = photo_bg()
        if ph:
            img = ph
            fg, muted = (255, 255, 255), (230, 230, 230)
    d = ImageDraw.Draw(img)
    maxw = W - 2 * M
    lay = pin.get("layout", "titel")
    y = 150
    if pin.get("kicker"):
        fk = font(fs, "medium", 40)
        d.text((W / 2, y), pin["kicker"].upper(), font=fk, fill=acc, anchor="mt")
        y += 90
    if lay in ("titel", "frage"):
        ft = fit(d, fs, "bold", pin["titel"], maxw, 150 if lay == "titel" else 120, 60, 5)
        block_h = len(wrap(d, words(pin["titel"]), ft, maxw)) * ft.size * 1.12
        y = max(y, (H - block_h) / 2 - 80)
        y = draw_rich(d, y, pin["titel"], ft, fg, acc, maxw, up)
        if pin.get("unterzeile"):
            fu = font(fs, "italic", 46)
            draw_rich(d, y + 50, pin["unterzeile"], fu, muted, acc, maxw, False, lh=1.35)
    else:
        ft = fit(d, fs, "bold", pin["titel"], maxw, 96, 50, 3)
        items = pin.get("punkte", [])
        title_h = len(wrap(d, words(pin["titel"]), ft, maxw)) * ft.size * 1.12 + 70
        top, bottom = y, H - 200
        size = 64
        while size > 30:
            fi = font(fs, "medium", size)
            need = sum(len(wrap(d, words(p), fi, maxw - 110)) * size * 1.3 + size * 0.7 for p in items)
            if need + title_h <= bottom - top:
                break
            size -= 2
        y = top + (bottom - top - need - title_h) / 2  # Block vertikal zentrieren
        y = draw_rich(d, y, pin["titel"], ft, fg, acc, maxw, up) + 70
        fi = font(fs, "medium", size)
        fn = font(fs, "bold", int(size * 1.05))
        r = size * 0.62
        for i, p in enumerate(items, 1):
            cx, cy = M + r, y + size * 0.62
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=acc)
            if lay == "schritte":
                d.text((cx, cy), str(i), font=fn, fill=bg, anchor="mm")
            else:
                k = r / 32
                d.line([(cx - 14 * k, cy + 1 * k), (cx - 4 * k, cy + 12 * k), (cx + 15 * k, cy - 11 * k)], fill=bg,
                       width=max(4, int(7 * k)))
            yy = y
            for line in wrap(d, words(p), fi, maxw - 110):
                xx = M + 2 * r + 36
                for w, a in line:
                    d.text((xx, yy), w, font=fi, fill=acc if a else fg)
                    xx += d.textlength(w + " ", font=fi)
                yy += size * 1.3
            y = yy + size * 0.7
    fb = font(fs, "bold", 40)
    name = CFG["marke"]
    base, end = name.rsplit(".", 1)
    tw = d.textlength(base, font=fb) + d.textlength("." + end, font=fb)
    x = (W - tw) / 2
    d.text((x, H - 110), base, font=fb, fill=fg)
    d.text((x + d.textlength(base, font=fb), H - 110), "." + end, font=fb, fill=acc)
    img.save(out, optimize=True)


def main():
    spec = Path(sys.argv[1])
    pins = json.loads(spec.read_text())
    rows = []
    for i, pin in enumerate(pins, 1):
        out = spec.parent / f"pin_{i:02d}.png"
        render(pin, out)
        rows.append({"Title": pin["pin_titel"][:100], "Media URL": "", "Pinterest board": pin.get("board", ""),
                     "Description": pin["beschreibung"][:500], "Link": pin.get("link", CFG["link"]),
                     "Keywords": pin.get("keywords", ""), "Alt text": pin.get("alt", ""), "Datei": out.name})
        print("Pin:", out)
    with open(spec.parent / "pins.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("Texte:", spec.parent / "pins.csv")


if __name__ == "__main__":
    main()
