"""Kinetic-Typography-Werbevideo fuer ein Hochzeits-Fotoalbum im Web.

Erzeugt out/werbung_16x9.mp4 und out/werbung_9x16.mp4 (60 fps) inkl. Sprecher,
Ticks, Riser und Hit, gemastert auf -14 LUFS / -1 dBTP.

Aufruf: python3 build.py            (beide Formate)
        python3 build.py 9x16       (nur ein Format)
Benoetigt: ffmpeg, espeak-ng + mbrola-de7, Pillow, numpy.
Echte Assets: assets/hook.jpg (Slot A) und assets/app_screenshot.png (Slot C)
ersetzen automatisch die Platzhalter, wenn vorhanden.
"""
import json
import math
import subprocess
import sys
import wave
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
ASSETS, OUT, TMP = ROOT / "assets", ROOT / "out", ROOT / "build_tmp"
FPS, SR = 60, 48000
ACCENT = (0xD9, 0x63, 0x3A)
BLACK, GREY, WHITE = (17, 17, 17), (128, 128, 128), (255, 255, 255)
FONTS = {
    "bold": ROOT / "fonts/InterTight-ExtraBold.ttf",
    "medium": ROOT / "fonts/InterTight-Medium.ttf",
    "light": ROOT / "fonts/InterTight-LightItalic.ttf",
}
VOICE = ["espeak-ng", "-v", "mb-de7", "-s", "205", "-p", "48"]

# Jede Phrase: (Anzeige, Aussprache, Akzentfarbe?)
PHRASES = {
    "hook1": [("Was", "Was", 0), ("passiert,", "passiert,", 0), ("wenn …", "wenn", 0)],
    "hook2": [("eure", "eure", 0), ("Fotos", "Fotos", 0), ("auf", "auf", 0), ("hundert", "hundert", 0),
              ("Handys", "Händis", 0), ("verschwinden?", "verschwinden?", 1)],
    "turn1": [("Was,", "Was,", 0), ("wenn", "wenn", 0), ("jedes", "jedes", 0)],
    "turn2": [("Handyfoto", "Händifoto", 1)],
    "turn3": [("zu", "zu", 0), ("einem", "einem", 0), ("gemeinsamen", "gemeinsamen", 0),
              ("Album", "Album", 0), ("wird?", "wird?", 0)],
    "list1": [("QR-Code", "Kuh Er Code", 0), ("scannen.", "scannen.", 0)],
    "list2": [("Ohne", "Ohne", 0), ("App,", "Äpp,", 0), ("ohne", "ohne", 0), ("Konto.", "Konto.", 0)],
    "list3": [("Jedes", "Jedes", 0), ("Foto", "Foto", 0), ("mit", "mit", 0), ("Namen.", "Namen.", 0)],
    "list4": [("Alles", "Alles", 0), ("an", "an", 0), ("einem", "einem", 0), ("Ort.", "Ort.", 0)],
    "pay": [("Euer", "Euer", 0), ("Album.", "Album.", 1)],
    "cta": [("Erst", "Erst", 0), ("kostenlos", "kostenlos", 1), ("ansehen.", "ansehen.", 0)],
    "price": [("Ab", "Ab", 0), ("29", "neunundzwanzig", 0), ("€", "Euro.", 0)],
}
BRAND, BRAND_END = "MARKE", ".de"  # Platzhalter fuer Marke/URL


# ------------------------------------------------------------------ Easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def spring(x):
    """easeOutBack mit ca. 3 % Ueberschwinger."""
    x = clamp(x)
    c1 = 0.9
    c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


# ------------------------------------------------------------------ Voice + Timing
def read_wav(path):
    with wave.open(str(path)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        return data, w.getframerate()


def tts(text, name):
    raw = TMP / f"{name}_raw.wav"
    out = TMP / f"{name}.wav"
    subprocess.run(VOICE + ["-w", str(raw), text], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-ar", str(SR), "-ac", "1", str(out)],
                   check=True)
    data, _ = read_wav(out)
    loud = np.where(np.abs(data) > 0.02)[0]
    return data[max(0, loud[0] - 200): loud[-1] + 400]


def build_voice():
    """Spricht alle Phrasen und schaetzt Wortzeiten (proportional zur Einzelwortlaenge)."""
    TMP.mkdir(exist_ok=True)
    clips, words = {}, {}
    for key, toks in PHRASES.items():
        audio = tts(" ".join(s for _, s, _ in toks), key)
        lens = [len(tts(s, f"{key}_w{i}")) for i, (_, s, _) in enumerate(toks)]
        total, acc, starts = sum(lens), 0, []
        for n in lens:
            starts.append(acc / total * len(audio) / SR)
            acc += n
        clips[key] = audio
        words[key] = starts
    return clips, words


def build_timeline(clips):
    d = {k: len(v) / SR for k, v in clips.items()}
    T = {}
    T["hook1"] = 0.30
    T["hook2"] = T["hook1"] + d["hook1"] + 0.22
    T["s2"] = T["hook2"] + d["hook2"] + 0.15
    T["turn1"] = T["s2"] + 0.50
    T["turn2"] = T["turn1"] + d["turn1"] + 0.05
    T["turn3"] = T["turn2"] + d["turn2"] + 0.10
    T["s3"] = T["turn3"] + d["turn3"] + 0.25
    t = T["s3"] + 0.20
    T["beats"] = []
    for i in range(1, 5):
        T[f"list{i}"] = t
        T["beats"].append(t)
        t += max(1.5, d[f"list{i}"] + 0.30)
    T["s4"] = t - 0.15
    T["pay"] = T["s4"] + 0.35
    T["s5"] = T["pay"] + d["pay"] + 0.55
    T["cta"] = T["s5"] + 0.20
    T["end"] = T["cta"] + d["cta"] + 0.25
    T["price"] = T["end"] + 0.15
    T["brand"] = T["price"] + 0.25
    T["total"] = max(T["price"] + d["price"], T["brand"]) + 1.1
    return T


# ------------------------------------------------------------------ Audio
def synth_tick():
    t = np.arange(int(0.05 * SR)) / SR
    return (np.sin(2 * np.pi * 1900 * t) * 0.6 + np.random.default_rng(1).normal(0, 0.15, t.size)) \
        * np.exp(-t / 0.008) * 0.35


def synth_riser(dur=0.9):
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(2).normal(0, 1, n)
    out, y = np.zeros(n), 0.0
    for i in range(n):  # Tiefpass mit steigender Grenzfrequenz
        a = 0.02 + 0.5 * (i / n) ** 2
        y += a * (noise[i] - y)
        out[i] = y
    freq = 220 + 660 * (t / dur) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(freq) / SR) * 0.25
    env = (t / dur) ** 2.2
    return (out * 0.5 + tone) * env * 0.35


def synth_hit():
    t = np.arange(int(0.7 * SR)) / SR
    f = 45 + 70 * np.exp(-t / 0.04)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.18)
    click = np.random.default_rng(3).normal(0, 1, t.size) * np.exp(-t / 0.01) * 0.3
    return (body + click) * 0.6


def build_audio(clips, words, T, path):
    mix = np.zeros(int((T["total"] + 0.5) * SR), dtype=np.float32)

    def put(sig, at):
        i = int(at * SR)
        mix[i:i + len(sig)] += sig[: len(mix) - i]

    for key, clip in clips.items():
        put(clip, T[key])
    for b in T["beats"]:
        put(synth_tick(), b)
    hit_at = T["pay"] + words["pay"][1]
    riser = synth_riser()
    put(riser, hit_at - len(riser) / SR)
    put(synth_hit(), hit_at)
    pcm = TMP / "mix_raw.wav"
    with wave.open(str(pcm), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(mix / max(1.0, np.abs(mix).max()), -1, 1) * 32767).astype(np.int16).tobytes())
    # Zwei-Pass-Loudnorm auf -14 LUFS / -1 dBTP
    res = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(pcm), "-af",
                          "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = json.loads(res[res.rindex("{"):])
    af = ("loudnorm=I=-14:TP=-1:LRA=11:linear=true:"
          f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(pcm), "-af", af, "-ar", str(SR),
                    "-ac", "2", str(path)], check=True)


# ------------------------------------------------------------------ Assets (Platzhalter)
def placeholder_hook(size=2600):
    """Goldene-Stunde-Platzhalter (Hochzeitsbogen-Silhouette), bis ein echtes Foto vorliegt."""
    h = w = size
    y = np.linspace(0, 1, h)[:, None]
    x = np.linspace(0, 1, w)[None, :]
    stops = [(0.0, (38, 36, 78)), (0.35, (150, 80, 95)), (0.55, (238, 140, 80)), (0.64, (255, 205, 140))]
    img = np.zeros((h, w, 3))
    for c in range(3):
        img[..., c] = np.interp(y, [s[0] for s in stops], [s[1][c] for s in stops])
    glow = np.exp(-(((x - 0.5) / 0.22) ** 2 + ((y - 0.63) / 0.12) ** 2))
    img += glow[..., None] * np.array([90, 70, 30])
    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(pil, "RGBA")
    rng = np.random.default_rng(7)
    for _ in range(70):  # Bokeh
        cx, cy, r = rng.uniform(0, w), rng.uniform(0.1 * h, 0.6 * h), rng.uniform(12, 55)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 225, 170, int(rng.uniform(15, 45))))
    pil = pil.filter(ImageFilter.GaussianBlur(4))
    d = ImageDraw.Draw(pil)
    sil = (28, 20, 26)
    pts = [(0, 0.66 * h)] + [(i, 0.66 * h + 18 * math.sin(i / 260)) for i in range(0, w + 1, 40)] + [(w, h), (0, h)]
    d.polygon(pts, fill=sil)
    ax, top, base, half = w / 2, 0.36 * h, 0.67 * h, 0.12 * w  # Bogen
    for sx in (ax - half, ax + half):
        d.rectangle([sx - 14, top + half, sx + 14, base], fill=sil)
    d.arc([ax - half, top, ax + half, top + 2 * half], 180, 360, fill=sil, width=30)
    for _ in range(140):  # Blumen am Bogen
        a = rng.uniform(math.pi, 2 * math.pi)
        r = rng.uniform(18, 40)
        px, py = ax + half * math.cos(a), top + half + half * math.sin(a)
        d.ellipse([px - r, py - r, px + r, py + r], fill=sil)
    grain = np.random.default_rng(9).normal(0, 4, (h, w, 1))
    arr = np.clip(np.asarray(pil).astype(np.float32) + grain, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def load_hook():
    p = ASSETS / "hook.jpg"
    if p.exists():
        return Image.open(p).convert("RGB")
    ph = ASSETS / "hook_placeholder.jpg"
    if not ph.exists():
        placeholder_hook().save(ph, quality=92)
    return Image.open(ph).convert("RGB")


def rounded_mask(size, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], r, fill=255)
    return m


def cover(img, size):
    sw, sh = size
    scale = max(sw / img.width, sh / img.height)
    im = img.resize((math.ceil(img.width * scale), math.ceil(img.height * scale)), Image.LANCZOS)
    l, t = (im.width - sw) // 2, (im.height - sh) // 2
    return im.crop((l, t, l + sw, t + sh))


def placeholder_app(hook):
    """Nachgebauter Album-Screen im Handyrahmen (Platzhalter fuer den echten Screenshot)."""
    W, H = 900, 1900
    sw, sh, inset = W - 44, H - 44, 22
    scr = Image.new("RGB", (sw, sh), (250, 248, 245))
    head = cover(hook, (sw, int(sh * 0.34)))
    shade = Image.linear_gradient("L").resize(head.size)
    head = Image.composite(Image.new("RGB", head.size, (0, 0, 0)), head, shade.point(lambda v: int(v * 0.55)))
    scr.paste(head, (0, 0))
    d = ImageDraw.Draw(scr)
    f = lambda k, s: ImageFont.truetype(str(FONTS[k]), s)
    d.text((48, head.height - 150), "Anna & Jonas", font=f("bold", 76), fill=WHITE)
    d.text((50, head.height - 62), "14. Juni 2026", font=f("medium", 38), fill=(235, 230, 225))
    y = head.height + 40
    d.text((48, y), "Euer Hochzeitsalbum", font=f("bold", 40), fill=BLACK)
    d.text((48, y + 52), "248 Fotos von 37 Gästen", font=f("medium", 30), fill=GREY)
    tiles = [((0.3, 0.55), "Lisa", (1.0, 0.9, 0.8)), ((0.7, 0.62), "Tom", (0.9, 0.95, 1.0)),
             ((0.5, 0.45), "Oma Ruth", (1.0, 0.85, 0.85)), ((0.2, 0.7), "Ben", (0.95, 1.0, 0.9)),
             ((0.8, 0.4), "Mara", (1.0, 0.95, 0.85)), ((0.45, 0.75), "Jan", (0.9, 0.9, 1.0))]
    tw, th, gap, x0, y0 = (sw - 48 * 2 - 24) // 2, 340, 24, 48, y + 120
    for i, ((cx, cy), name, tint) in enumerate(tiles):
        col, row = i % 2, i // 2
        crop_w = hook.width * 0.35
        box = (int(hook.width * cx - crop_w / 2), int(hook.height * cy - crop_w * th / tw / 2))
        tile = hook.crop((box[0], box[1], box[0] + int(crop_w), box[1] + int(crop_w * th / tw))).resize((tw, th))
        tile = Image.fromarray(np.clip(np.asarray(tile) * np.array(tint), 0, 255).astype(np.uint8))
        px, py = x0 + col * (tw + gap), y0 + row * (th + 70)
        scr.paste(tile, (px, py), rounded_mask((tw, th), 22))
        d.text((px + 4, py + th + 12), f"von {name}", font=f("medium", 28), fill=(90, 90, 90))
    bw, bh = sw - 96, 110
    d.rounded_rectangle([48, sh - bh - 60, 48 + bw, sh - 60], 55, fill=ACCENT)
    d.text((sw // 2, sh - 60 - bh // 2), "Fotos hochladen", font=f("bold", 42), fill=WHITE, anchor="mm")
    phone = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(phone).rounded_rectangle([0, 0, W - 1, H - 1], 120, fill=(20, 20, 22, 255))
    phone.paste(scr, (inset, inset), rounded_mask((sw, sh), 100))
    return phone


def load_card(hook):
    p = ASSETS / "app_screenshot.png"
    if p.exists():
        shot = Image.open(p).convert("RGB")
        W = 900
        H = int(W * shot.height / shot.width)
        phone = Image.new("RGBA", (W, H + 44), (0, 0, 0, 0))
        ImageDraw.Draw(phone).rounded_rectangle([0, 0, W - 1, H + 43], 120, fill=(20, 20, 22, 255))
        phone.paste(shot.resize((W - 44, H)), (22, 22), rounded_mask((W - 44, H), 100))
        return phone
    ph = ASSETS / "app_card_placeholder.png"
    if not ph.exists():
        placeholder_app(hook).save(ph)
    return Image.open(ph).convert("RGBA")


# ------------------------------------------------------------------ Text
_font_cache, _word_cache = {}, {}


def font(kind, size):
    k = (kind, size)
    if k not in _font_cache:
        _font_cache[k] = ImageFont.truetype(str(FONTS[kind]), size)
    return _font_cache[k]


def tracking(kind, size):
    return -0.025 * size if kind == "bold" else -0.005 * size


def word_width(text, kind, size):
    f = font(kind, size)
    return f.getlength(text) + tracking(kind, size) * (len(text) - 1)


def word_img(text, kind, size, color):
    k = (text, kind, size, color)
    if k not in _word_cache:
        f = font(kind, size)
        asc, desc = f.getmetrics()
        pad = int(size * 0.15)
        im = Image.new("RGBA", (int(word_width(text, kind, size)) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        tr = tracking(kind, size)
        for i, ch in enumerate(text):
            d.text((pad + f.getlength(text[:i]) + tr * i, pad), ch, font=f, fill=color)
        _word_cache[k] = (im, pad)
    return _word_cache[k]


def layout(groups, cx, cy, max_w):
    """groups: Liste von (tokens, kind, size, color, t0_words, line_gap_factor).
    Gibt platzierte Woerter zurueck: (x, y, text, kind, size, color, t_appear)."""
    lines = []
    for toks, kind, size, color, times, lg in groups:
        while size > 20:  # schrumpfen, bis jedes Einzelwort passt
            if max(word_width(t[0], kind, size) for t in toks) <= max_w:
                break
            size -= 2
        space = font(kind, size).getlength(" ") * 0.9
        cur, cur_w = [], 0
        for tok, tm in zip(toks, times):
            ww = word_width(tok[0], kind, size)
            if cur and cur_w + space + ww > max_w:
                lines.append((cur, cur_w, kind, size, lg))
                cur, cur_w = [], 0
            cur_w += (space if cur else 0) + ww
            cur.append((tok, tm, ww, space, color))
        lines.append((cur, cur_w, kind, size, lg))
    heights = [size * lg for _, _, _, size, lg in lines]
    y = cy - sum(heights) / 2
    placed = []
    for (cur, cur_w, kind, size, lg), lh in zip(lines, heights):
        asc, desc = font(kind, size).getmetrics()
        x = cx - cur_w / 2
        top = y + (lh - (asc + desc)) / 2
        for tok, tm, ww, space, color in cur:
            c = ACCENT if tok[2] else color
            placed.append((x, top, tok[0], kind, size, c, tm))
            x += ww + space
        y += lh
    return placed


def draw_words(frame, placed, t, alpha=1.0, dy=0.0):
    for x, y, text, kind, size, color, ta in placed:
        if t < ta:
            continue
        p = ease_out((t - ta) / 0.10)
        s = 0.92 + 0.08 * p
        a = clamp((t - ta) / 0.06) * alpha
        if a <= 0:
            continue
        im, pad = word_img(text, kind, size, color)
        if s < 0.999:
            im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BICUBIC)
        if a < 0.999:
            im = im.copy()
            im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
        w0, h0 = word_img(text, kind, size, color)[0].size
        px = x - pad + (w0 - im.width) / 2
        py = y - pad + (h0 - im.height) / 2 + dy
        frame.alpha_composite(im, (int(round(px)), int(round(py))))


# ------------------------------------------------------------------ Szene: Perspektive
def perspective_coeffs(src, dst):
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    A = np.array(m, dtype=float)
    B = np.array([c for p in src for c in p], dtype=float)
    return np.linalg.solve(A, B).tolist()


def tilted(card, angle):
    """Dreht die Karte um die Y-Achse (Naeherung per Perspektive)."""
    w, h = card.size
    if abs(angle) < 0.05:
        return card, 0
    k = math.sin(math.radians(angle)) * 0.22
    nw = w * math.cos(math.radians(angle))
    pad = int(h * k) + 2
    W2, H2 = int(nw) + 2, h + 2 * pad
    dst = [(0, pad - h * k), (nw, pad + h * k), (nw, pad + h - h * k), (0, pad + h + h * k)]
    dst = [(x, y) for x, y in dst]
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    out = card.transform((W2, H2), Image.PERSPECTIVE, perspective_coeffs(src, dst), Image.BICUBIC)
    return out, pad


# ------------------------------------------------------------------ Renderer
class Ad:
    def __init__(self, fmt, T, words, hook, card):
        self.W, self.H = (1920, 1080) if fmt == "16x9" else (1080, 1920)
        self.fmt, self.T = fmt, T
        W, H = self.W, self.H
        self.mx, self.my = int(0.10 * W), int(0.12 * H)
        self.max_w = W - 2 * self.mx
        self.cx, self.cy = W / 2, H / 2
        self.hook = cover(hook, (int(W * 1.1), int(H * 1.1)))
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        vig = np.clip(1 - 0.45 * np.clip(r - 0.45, 0, None) ** 1.6, 0, 1)
        self.vignette = Image.fromarray((vig * 255).astype(np.uint8))
        tw = lambda key: [T[key] + s for s in words[key]]
        big = 132 if fmt == "16x9" else 112
        self.hook_words = layout([
            (PHRASES["hook1"], "bold", int(big * 0.62), WHITE, tw("hook1"), 1.35),
            (PHRASES["hook2"], "bold", big, WHITE, tw("hook2"), 1.12)], self.cx, self.cy, self.max_w)
        self.turn_words = layout([
            (PHRASES["turn1"], "medium", 54, GREY, tw("turn1"), 1.5),
            (PHRASES["turn2"], "bold", 230, BLACK, tw("turn2"), 1.05),
            (PHRASES["turn3"], "light", 56, (60, 60, 60), tw("turn3"), 1.5)], self.cx, self.cy, self.max_w)
        # Liste
        arrow_gap = 0.35
        size = 124 if fmt == "16x9" else 110
        while True:
            widths = [word_width(" ".join(t[0] for t in PHRASES[f"list{i}"]), "bold", size) for i in range(1, 5)]
            aw = word_width("→", "bold", size)
            if max(widths) / 2 + aw * (1 + arrow_gap) <= self.max_w / 2:
                break
            size -= 2
        self.list_size, self.list_lh = size, size * 1.32
        self.list_lines = []
        for i in range(1, 5):
            text = " ".join(t[0] for t in PHRASES[f"list{i}"])
            im, pad = word_img(text, "bold", size, BLACK)
            bp = 16
            base = Image.new("RGBA", (im.width + 2 * bp, im.height + 2 * bp), (0, 0, 0, 0))
            base.alpha_composite(im, (bp, bp))
            blurs = [base] + [base.filter(ImageFilter.GaussianBlur(r)) for r in range(1, 13)]
            self.list_lines.append(blurs)
        self.arrow, self.arrow_pad = word_img("→", "bold", size, ACCENT)
        self.arrow_off = widths  # Textbreiten fuer Pfeilposition
        # Payoff + Karte
        if fmt == "16x9":
            pay_cx, pay_cy, pay_w = W * 0.34, H / 2, W * 0.42
            ch = int(H * 0.80)
            self.card_c = (W * 0.73, H / 2)
        else:
            pay_cx, pay_cy, pay_w = W / 2, H * 0.25, self.max_w
            ch = int(H * 0.52)
            self.card_c = (W / 2, H * 0.62)
        self.pay_words = layout([(PHRASES["pay"], "bold", 170 if fmt == "16x9" else 150, BLACK, tw("pay"), 1.1)],
                                pay_cx, pay_cy, pay_w)
        cw = int(card.width * ch / card.height)
        self.card = card.resize((cw, ch), Image.LANCZOS)
        sh = Image.new("RGBA", (cw + 160, ch + 160), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([80, 100, 80 + cw, 100 + ch], int(cw * 0.13), fill=(0, 0, 0, 70))
        self.shadow = sh.filter(ImageFilter.GaussianBlur(28))
        self.cta_words = layout([(PHRASES["cta"], "bold", 140 if fmt == "16x9" else 118, BLACK, tw("cta"), 1.15)],
                                self.cx, self.cy, self.max_w)
        self.price_words = layout([(PHRASES["price"], "medium", 52, GREY, tw("price"), 1.4)],
                                  self.cx, self.cy - 70, self.max_w)
        bs = 150 if fmt == "16x9" else 140
        (x1, y1, *r1), (_, y2, *r2) = layout([([(BRAND, "", 0), (BRAND_END, "", 1)], "bold", bs, BLACK,
                                               [T["brand"], T["brand"]], 1.1)], self.cx, self.cy + 40, self.max_w)
        # ".de" direkt anschliessen (ohne Leerzeichen), Gesamtbreite zentriert
        bw = word_width(BRAND, "bold", r1[2])
        x1 = self.cx - (bw + word_width(BRAND_END, "bold", r1[2])) / 2
        self.brand_words = [(x1, y1, *r1), (x1 + bw, y2, *r2)]

    # --------------------------------------------------------------
    def frame(self, t):
        T, W, H = self.T, self.W, self.H
        f = Image.new("RGBA", (W, H), WHITE + (255,))
        # Szene 1/2: Foto
        if t < T["s2"] + 0.8:
            z = 1 + 0.08 * ease_io(t / (T["s2"] + 0.8))
            hw, hh = self.hook.size  # self.hook ist 110 % gross, sichtbarer Ausschnitt schrumpft mit z
            vw, vh = hw / 1.1 / z, hh / 1.1 / z
            ph = self.hook.resize((W, H), Image.BILINEAR,
                                  box=((hw - vw) / 2, (hh - vh) / 2, (hw + vw) / 2, (hh + vh) / 2))
            ph = ImageChops.multiply(ph, Image.merge("RGB", [self.vignette] * 3))
            p2 = clamp((t - T["s2"]) / 0.5)
            if p2 > 0:
                ph = ph.filter(ImageFilter.GaussianBlur(40 * ease_io(p2)))
            f.paste(ph, (0, 0))
            if t < T["s2"] + 0.2:
                draw_words(f, self.hook_words, t, alpha=1 - clamp((t - T["s2"]) / 0.2))
            if p2 > 0:  # weicher Wisch von unten nach Weiss
                soft = 0.35 * H
                edge = H + soft - ease_io(clamp((t - T["s2"] - 0.05) / 0.45)) * (H + 2 * soft)
                g = np.clip((np.arange(H) - edge) / soft + 0.5, 0, 1)
                mask = Image.fromarray((np.repeat(g[:, None], W, 1) * 255).astype(np.uint8))
                f.paste(Image.new("RGBA", (W, H), WHITE + (255,)), (0, 0), mask)
        # Szene 2
        if T["s2"] <= t < T["s3"] + 0.3:
            draw_words(f, self.turn_words, t, alpha=1 - clamp((t - T["s3"]) / 0.25))
        # Szene 3: Liste
        if T["s3"] <= t < T["s4"] + 0.3:
            self.draw_list(f, t)
        # Szene 4: Payoff + Karte
        if T["s4"] <= t < T["s5"] + 0.3:
            a = 1 - clamp((t - T["s5"]) / 0.25)
            draw_words(f, self.pay_words, t, alpha=a)
            self.draw_card(f, t, a)
        # Szene 5: CTA + Endcard
        if T["s5"] <= t:
            draw_words(f, self.cta_words, t, alpha=1 - clamp((t - T["end"]) / 0.2))
            if t >= T["end"]:
                draw_words(f, self.price_words, t)
                draw_words(f, self.brand_words, t)
        return f.convert("RGB")

    def draw_list(self, f, t):
        T = self.T
        pos = -1.0
        for k, b in enumerate(T["beats"]):
            if t >= b:
                pos = (k - 1) + spring((t - b) / 0.45)
        fade_in = ease_out((t - T["s3"]) / 0.3)
        fade_out = 1 - clamp((t - T["s4"]) / 0.25)
        for i, blurs in enumerate(self.list_lines):
            d = clamp(abs(i - pos))
            r = int(round(12 * d))
            sc = 1 - 0.08 * d
            op = (1 - 0.72 * d) * fade_in * fade_out
            im = blurs[r]
            if sc < 0.999:
                im = im.resize((int(im.width * sc), int(im.height * sc)), Image.BICUBIC)
            if op < 0.999:
                im = im.copy()
                im.putalpha(im.getchannel("A").point(lambda v: int(v * op)))
            y = self.cy + (i - pos) * self.list_lh
            f.alpha_composite(im, (int(self.cx - im.width / 2), int(y - im.height / 2)))
            if d < 1:
                aa = (1 - d) * fade_out
                ar = self.arrow.copy()
                ar.putalpha(ar.getchannel("A").point(lambda v: int(v * aa)))
                tw = self.arrow_off[i] * sc
                ax = self.cx - tw / 2 - self.list_size * 0.35 - ar.width + self.arrow_pad
                f.alpha_composite(ar, (int(ax), int(y - ar.height / 2)))

    def draw_card(self, f, t, alpha):
        T = self.T
        p = (t - T["s4"] - 0.15) / 0.6
        if p <= 0:
            return
        slide = ease_out(p)
        angle = 24 * (1 - ease_out((t - T["s4"] - 0.15) / 0.8))
        card, pad = tilted(self.card, angle)
        cx, cy = self.card_c
        x = cx + (1 - slide) * self.W * 0.7 - card.width / 2
        y = cy - card.height / 2
        sh = self.shadow
        if alpha < 1:
            card = card.copy()
            card.putalpha(card.getchannel("A").point(lambda v: int(v * alpha)))
            sh = sh.copy()
            sh.putalpha(sh.getchannel("A").point(lambda v: int(v * alpha)))
        f.alpha_composite(sh, (int(cx + (1 - slide) * self.W * 0.7 - self.card.width / 2 - 80),
                               int(cy - self.card.height / 2 - 80)))
        f.alpha_composite(card, (int(x), int(y)))


_AD = None


def _init(fmt, T, words, hook, card):
    global _AD
    _AD = Ad(fmt, T, words, hook, card)


def _render(i):
    return _AD.frame(i / FPS).tobytes()


def render(fmt, T, words, hook, card, audio):
    W, H = (1920, 1080) if fmt == "16x9" else (1080, 1920)
    path = OUT / f"werbung_{fmt}.mp4"
    n = int(T["total"] * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", str(audio), "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(4, initializer=_init, initargs=(fmt, T, words, hook, card)) as pool:
        for k, buf in enumerate(pool.imap(_render, range(n), chunksize=4)):
            proc.stdin.write(buf)
            if k % 120 == 0:
                print(f"  {fmt}: {k}/{n}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("fertig:", path)


def main():
    fmts = sys.argv[1:] or ["16x9", "9x16"]
    ASSETS.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    clips, words = build_voice()
    T = build_timeline(clips)
    print("Laenge: %.2f s" % T["total"])
    audio = TMP / "mix.wav"
    build_audio(clips, words, T, audio)
    hook = load_hook()
    card = load_card(hook)
    for fmt in fmts:
        render(fmt, T, words, hook, card, audio)


if __name__ == "__main__":
    main()
