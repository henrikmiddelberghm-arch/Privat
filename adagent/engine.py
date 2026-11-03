"""Video-Engine des Ad-Agenten: rendert eine Spezifikation (JSON) zu 60-fps-Videos.

  python3 engine.py specs/ad_001.json --check     Timeline + Warnungen, kein Rendern
  python3 engine.py specs/ad_001.json --preview   Kontaktbogen mit Standbildern (schnell)
  python3 engine.py specs/ad_001.json             Videos rendern (alle Formate aus der Spec)

Spec-Aufbau: siehe SPEC.md.
"""
import argparse
import hashlib
import json
import math
import re
import subprocess
import wave
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent
PATTERNS = json.loads((ROOT / "patterns.json").read_text())
FONTSETS = {f["id"]: f for f in PATTERNS["fonts"]}
THEMES = {t["id"]: t for t in PATTERNS["themes"]}
PACING = {p["id"]: p for p in PATTERNS["pacing"]}
TMP, OUT, ASSETS = ROOT / "build_tmp", ROOT / "out", ROOT / "assets"
FPS, SR, TD = 60, 48000, 0.4  # Bildrate, Abtastrate, Uebergangsdauer

# Aussprache-Korrekturen fuer die deutsche Entwurfsstimme (nur fuer TTS, nicht fuer die Anzeige)
PRON = {"handy": "Händi", "handys": "Händis", "handyfoto": "Händifoto", "handyfotos": "Händifotos",
        "app": "Äpp", "apps": "Äpps", "qr-code": "Kuh Er Code", "qr": "Kuh Er", "€": "Euro",
        "download": "Daunlohd", "upload": "Applohd", "online": "onlein", "web": "Wepp", "link": "Link"}


# ------------------------------------------------------------------ Hilfen
def hexc(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    return 1 - (1 - clamp(x)) ** 3


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def spring(x, c1=0.9):  # easeOutBack, c1=0.9 -> ca. 3 % Ueberschwinger
    x = clamp(x)
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def mix(a, b, k):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


def with_alpha(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return im


def rounded_mask(size, r):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], r, fill=255)
    return m


def cover(img, size):
    sw, sh = size
    s = max(sw / img.width, sh / img.height)
    im = img.resize((math.ceil(img.width * s), math.ceil(img.height * s)), Image.LANCZOS)
    l, t = (im.width - sw) // 2, (im.height - sh) // 2
    return im.crop((l, t, l + sw, t + sh))


# ------------------------------------------------------------------ Stimme
def say_text(display):
    out = []
    for tok in display.split():
        core = tok.strip(".,!?:;…–-\"'()")
        if not core:
            continue
        rep = PRON.get(core.lower())
        out.append(tok.replace(core, rep) if rep else tok)
    return " ".join(out)


def tts(text, rate, pitch):
    """Spricht text mit espeak-ng/MBROLA, gibt Float-Samples (48 kHz, Stille getrimmt) zurueck. Mit Cache."""
    if not text.strip():
        return np.zeros(0, dtype=np.float32)
    TMP.mkdir(exist_ok=True)
    key = hashlib.md5(f"{text}|{rate}|{pitch}".encode()).hexdigest()[:16]
    out = TMP / f"tts_{key}.wav"
    if not out.exists():
        raw = TMP / f"tts_{key}_raw.wav"
        subprocess.run(["espeak-ng", "-v", "mb-de7", "-s", str(rate), "-p", str(pitch), "-w", str(raw), text],
                       check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-ar", str(SR), "-ac", "1",
                        str(out)], check=True)
    with wave.open(str(out)) as w:
        d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    loud = np.where(np.abs(d) > 0.02)[0]
    if len(loud) == 0:
        return np.zeros(0, dtype=np.float32)
    return d[max(0, loud[0] - 200): loud[-1] + 400]


class Line:
    """Eine gesprochene + angezeigte Textzeile."""

    def __init__(self, spec, default_role):
        if isinstance(spec, str):
            spec = {"text": spec}
        self.text = spec["text"]
        self.role = spec.get("role", default_role)
        self.accent = set(spec.get("accent", []))
        self.say = spec.get("say")
        self.silent = spec.get("silent", False)
        self.tokens = self.text.split()
        self.start = 0.0
        self.audio = None
        self.word_t = []

    def synth(self, rate, pitch):
        say_tokens = [say_text(t) for t in self.tokens]
        if self.silent:
            self.audio = np.zeros(0, dtype=np.float32)
            self.rel = [0.0] * len(self.tokens)
            return
        full = self.say if self.say else " ".join(s for s in say_tokens if s)
        self.audio = tts(full, rate, pitch)
        lens = [len(tts(s, rate, pitch)) if s else 0 for s in say_tokens]
        total = max(1, sum(lens))
        acc, rel = 0, []
        for n in lens:
            rel.append(acc / total * len(self.audio) / SR)
            acc += n
        self.rel = rel

    @property
    def dur(self):
        return len(self.audio) / SR

    def place(self, start):
        self.start = start
        self.word_t = [start + r for r in self.rel]
        return start + self.dur

    def is_accent(self, tok):
        return tok in self.accent or tok.strip(".,!?:;…") in self.accent


# ------------------------------------------------------------------ Text-Rendering
class Typo:
    ROLES = {  # role: (Schnitt, Groesse in U, Farbe, Zeilenhoehe)
        "small": ("bold", 0.62, "fg", 1.35), "big": ("bold", 1.15, "fg", 1.12),
        "huge": ("bold", 2.2, "accent", 1.05), "grey": ("medium", 0.6, "muted", 1.5),
        "italic": ("italic", 0.56, "fg", 1.5), "body": ("medium", 0.75, "fg", 1.3),
        "number": ("bold", 2.8, "accent", 1.0), "list": ("bold", 1.1, "fg", 1.32),
        "cta": ("bold", 1.25, "fg", 1.15), "price": ("medium", 0.52, "muted", 1.4),
        "brand": ("bold", 1.4, "fg", 1.1), "before": ("bold", 0.95, "muted", 1.15),
        "after": ("bold", 0.95, "bg", 1.15), "punch": ("bold", 3.2, "fg", 1.0),
    }

    def __init__(self, fontset):
        self.fs = fontset
        self._f, self._w = {}, {}

    def font(self, kind, size):
        k = (kind, size)
        if k not in self._f:
            self._f[k] = ImageFont.truetype(str(ROOT / "fonts" / self.fs[kind]), size)
        return self._f[k]

    def disp(self, text):
        return text.upper() if self.fs.get("upper") else text

    def tracking(self, kind, size):
        return (self.fs.get("tracking", 0) if kind == "bold" else -0.005) * size

    def width(self, text, kind, size):
        text = self.disp(text)
        return self.font(kind, size).getlength(text) + self.tracking(kind, size) * (len(text) - 1)

    def img(self, text, kind, size, color):
        text = self.disp(text)
        k = (text, kind, size, color)
        if k not in self._w:
            f = self.font(kind, size)
            asc, desc = f.getmetrics()
            pad = int(size * 0.15)
            w = int(self.width(text, kind, size)) + 2 * pad + 2
            im = Image.new("RGBA", (max(1, w), asc + desc + 2 * pad), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            tr = self.tracking(kind, size)
            for i, ch in enumerate(text):
                d.text((pad + f.getlength(text[:i]) + tr * i, pad), ch, font=f, fill=color)
            self._w[k] = (im, pad)
        return self._w[k]


class Placed:
    __slots__ = ("x", "y", "text", "kind", "size", "color", "t")

    def __init__(self, x, y, text, kind, size, color, t):
        self.x, self.y, self.text, self.kind, self.size, self.color, self.t = x, y, text, kind, size, color, t


def layout(ty, groups, cx, cy, max_w, U, pal):
    """groups: Liste von (Line, role). Zentriert, umbricht, verkleinert zu breite Einzelwoerter."""
    rows = []
    for line, role in groups:
        kind, fac, col, lh = Typo.ROLES[role]
        size = int(U * fac)
        while size > 18 and max(ty.width(t, kind, size) for t in line.tokens) > max_w:
            size -= 2
        space = ty.font(kind, size).getlength(" ") * 0.9
        cur, cw = [], 0
        for tok, tm in zip(line.tokens, line.word_t):
            ww = ty.width(tok, kind, size)
            if cur and cw + space + ww > max_w:
                rows.append((cur, cw, kind, size, lh))
                cur, cw = [], 0
            cw += (space if cur else 0) + ww
            color = pal["accent_word"] if line.is_accent(tok) else pal[col]
            cur.append((tok, tm, ww, space, color))
        rows.append((cur, cw, kind, size, lh))
    total_h = sum(size * lh for *_, size, lh in rows)
    y = cy - total_h / 2
    placed = []
    for cur, cw, kind, size, lh in rows:
        asc, desc = ty.font(kind, size).getmetrics()
        x = cx - cw / 2
        top = y + (size * lh - (asc + desc)) / 2
        for tok, tm, ww, space, color in cur:
            placed.append(Placed(x, top, tok, kind, size, color, tm))
            x += ww + space
        y += size * lh
    return placed


def draw_words(ty, frame, placed, t, alpha=1.0, pop=0.92):
    for p in placed:
        if t < p.t:
            continue
        a = clamp((t - p.t) / 0.06) * alpha
        if a <= 0:
            continue
        s = pop + (1 - pop) * ease_out((t - p.t) / 0.10)
        im0, pad = ty.img(p.text, p.kind, p.size, p.color)
        im = im0
        if s < 0.999:
            im = im0.resize((max(1, int(im0.width * s)), max(1, int(im0.height * s))), Image.BICUBIC)
        im = with_alpha(im, a)
        frame.alpha_composite(im, (int(round(p.x - pad + (im0.width - im.width) / 2)),
                                   int(round(p.y - pad + (im0.height - im.height) / 2))))


# ------------------------------------------------------------------ Assets (Platzhalter)
def placeholder_hook(seed=7, size=2600):
    rng = np.random.default_rng(seed)
    skies = [
        [(0.0, (38, 36, 78)), (0.35, (150, 80, 95)), (0.55, (238, 140, 80)), (0.64, (255, 205, 140))],
        [(0.0, (20, 34, 70)), (0.4, (70, 90, 150)), (0.58, (200, 150, 170)), (0.65, (250, 210, 190))],
        [(0.0, (60, 40, 70)), (0.38, (190, 110, 120)), (0.56, (250, 170, 110)), (0.64, (255, 225, 170))],
    ]
    stops = skies[seed % len(skies)]
    h = w = size
    y = np.linspace(0, 1, h)[:, None]
    x = np.linspace(0, 1, w)[None, :]
    img = np.zeros((h, w, 3))
    for c in range(3):
        img[..., c] = np.interp(y, [s[0] for s in stops], [s[1][c] for s in stops])
    sx = rng.uniform(0.35, 0.65)
    img += np.exp(-(((x - sx) / 0.22) ** 2 + ((y - 0.63) / 0.12) ** 2))[..., None] * np.array([90, 70, 30])
    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(pil, "RGBA")
    for _ in range(70):
        cx, cy, r = rng.uniform(0, w), rng.uniform(0.1 * h, 0.6 * h), rng.uniform(12, 55)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 225, 170, int(rng.uniform(15, 45))))
    pil = pil.filter(ImageFilter.GaussianBlur(4))
    d = ImageDraw.Draw(pil)
    sil = (28, 20, 26)
    pts = [(0, 0.66 * h)] + [(i, 0.66 * h + 18 * math.sin(i / 260 + seed)) for i in range(0, w + 1, 40)] + [(w, h), (0, h)]
    d.polygon(pts, fill=sil)
    ax, top, base, half = w / 2, 0.36 * h, 0.67 * h, 0.12 * w
    for px in (ax - half, ax + half):
        d.rectangle([px - 14, top + half, px + 14, base], fill=sil)
    d.arc([ax - half, top, ax + half, top + 2 * half], 180, 360, fill=sil, width=30)
    for _ in range(140):
        a = rng.uniform(math.pi, 2 * math.pi)
        r = rng.uniform(18, 40)
        px, py = ax + half * math.cos(a), top + half + half * math.sin(a)
        d.ellipse([px - r, py - r, px + r, py + r], fill=sil)
    arr = np.asarray(pil).astype(np.float32) + rng.normal(0, 4, (h, w, 1))
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def placeholder_app(hook, accent):
    W, H = 900, 1900
    sw, sh = W - 44, H - 44
    scr = Image.new("RGB", (sw, sh), (250, 248, 245))
    head = cover(hook, (sw, int(sh * 0.34)))
    shade = Image.linear_gradient("L").resize(head.size).point(lambda v: int(v * 0.55))
    head = Image.composite(Image.new("RGB", head.size, (0, 0, 0)), head, shade)
    scr.paste(head, (0, 0))
    d = ImageDraw.Draw(scr)
    f = lambda n, s: ImageFont.truetype(str(ROOT / "fonts" / n), s)
    d.text((48, head.height - 150), "Anna & Jonas", font=f("InterTight-ExtraBold.ttf", 76), fill=(255, 255, 255))
    d.text((50, head.height - 62), "14. Juni 2026", font=f("InterTight-Medium.ttf", 38), fill=(235, 230, 225))
    y = head.height + 40
    d.text((48, y), "Euer Hochzeitsalbum", font=f("InterTight-ExtraBold.ttf", 40), fill=(17, 17, 17))
    d.text((48, y + 52), "248 Fotos von 37 Gästen", font=f("InterTight-Medium.ttf", 30), fill=(128, 128, 128))
    tiles = [((0.3, 0.55), "Lisa", (1.0, 0.9, 0.8)), ((0.7, 0.62), "Tom", (0.9, 0.95, 1.0)),
             ((0.5, 0.45), "Oma Ruth", (1.0, 0.85, 0.85)), ((0.2, 0.7), "Ben", (0.95, 1.0, 0.9)),
             ((0.8, 0.4), "Mara", (1.0, 0.95, 0.85)), ((0.45, 0.75), "Jan", (0.9, 0.9, 1.0))]
    tw, th, gap, x0, y0 = (sw - 48 * 2 - 24) // 2, 340, 24, 48, y + 120
    for i, ((cx, cy), name, tint) in enumerate(tiles):
        cw = hook.width * 0.35
        bx, by = int(hook.width * cx - cw / 2), int(hook.height * cy - cw * th / tw / 2)
        tile = hook.crop((bx, by, bx + int(cw), by + int(cw * th / tw))).resize((tw, th))
        tile = Image.fromarray(np.clip(np.asarray(tile) * np.array(tint), 0, 255).astype(np.uint8))
        px, py = x0 + (i % 2) * (tw + gap), y0 + (i // 2) * (th + 70)
        scr.paste(tile, (px, py), rounded_mask((tw, th), 22))
        d.text((px + 4, py + th + 12), f"von {name}", font=f("InterTight-Medium.ttf", 28), fill=(90, 90, 90))
    d.rounded_rectangle([48, sh - 170, sw - 48, sh - 60], 55, fill=accent)
    d.text((sw // 2, sh - 115), "Fotos hochladen", font=f("InterTight-ExtraBold.ttf", 42), fill=(255, 255, 255),
           anchor="mm")
    phone = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(phone).rounded_rectangle([0, 0, W - 1, H - 1], 120, fill=(20, 20, 22, 255))
    phone.paste(scr, (22, 22), rounded_mask((sw, sh), 100))
    return phone


def load_assets(spec, accent):
    ASSETS.mkdir(exist_ok=True)
    a = spec.get("assets", {})
    if a.get("hook") and (ROOT / a["hook"]).exists():
        hook = Image.open(ROOT / a["hook"]).convert("RGB")
    else:
        seed = a.get("placeholder_seed", 7)
        p = ASSETS / f"hook_placeholder_{seed}.jpg"
        if not p.exists():
            placeholder_hook(seed).save(p, quality=92)
        hook = Image.open(p).convert("RGB")
    if a.get("screenshot") and (ROOT / a["screenshot"]).exists():
        shot = Image.open(ROOT / a["screenshot"]).convert("RGB")
        W = 900
        H = int((W - 44) * shot.height / shot.width)
        card = Image.new("RGBA", (W, H + 44), (0, 0, 0, 0))
        ImageDraw.Draw(card).rounded_rectangle([0, 0, W - 1, H + 43], 120, fill=(20, 20, 22, 255))
        card.paste(shot.resize((W - 44, H)), (22, 22), rounded_mask((W - 44, H), 100))
    else:
        card = placeholder_app(hook, accent)
    return hook, card


# ------------------------------------------------------------------ Szenen
class Scene:
    lead_cut = 0.12

    def __init__(self, spec, ad):
        self.spec, self.ad = spec, ad
        self.type = spec["type"]
        self.transition = spec.get("transition", "cut")
        self.bgkey = spec.get("bg", "bg")
        self.lines = [Line(l, self.default_role(i)) for i, l in enumerate(spec.get("lines", []))]

    def default_role(self, i):
        return "big"

    def all_lines(self):
        return self.lines

    def palette(self, th):
        bg, fg, muted, acc = (hexc(th[k]) for k in ("bg", "fg", "muted", "accent"))
        if self.bgkey == "accent":
            on = bg if sum(bg) > sum(fg) else fg
            return {"bgc": acc, "fg": on, "muted": mix(acc, on, 0.6), "accent": fg if on == bg else bg,
                    "accent_word": fg if on == bg else bg, "bg": acc}
        if self.bgkey == "fg":
            return {"bgc": fg, "fg": bg, "muted": mix(fg, bg, 0.55), "accent": acc, "accent_word": acc, "bg": fg}
        return {"bgc": bg, "fg": fg, "muted": muted, "accent": acc, "accent_word": acc, "bg": bg}

    def time(self, t0, pace):
        t = t0
        for i, l in enumerate(self.lines):
            t = l.place(t) + pace["gap"] + (0.18 if i == 0 and len(self.lines) > 1 else 0)
        self.end = t + 0.2
        return self.end

    def prepare(self, R):
        pass

    def background(self, R, t):
        return Image.new("RGBA", (R.W, R.H), self.pal["bgc"] + (255,))

    def draw(self, R, f, t):
        pass

    def beats(self):
        return []


class StatementScene(Scene):
    """Gestapelte Zeilen mit Rollen (small/big/huge/grey/italic/number ...)."""

    def default_role(self, i):
        return ["big", "big", "italic"][min(i, 2)]

    def prepare(self, R):
        self.placed = layout(R.ty, [(l, l.role) for l in self.lines], R.cx, R.cy, R.max_w, R.U, self.pal)
        self.numbers = {}
        for l in self.lines:
            if l.role == "number":
                m = re.search(r"\d+", l.text)
                if m:
                    self.numbers[l.text] = int(m.group())

    def draw(self, R, f, t):
        normal = [p for p in self.placed if not (p.text in self.numbers)]
        draw_words(R.ty, f, normal, t)
        for p in self.placed:
            if p.text in self.numbers and t >= p.t:
                n = self.numbers[p.text]
                v = int(round(n * ease_out((t - p.t) / 0.7)))
                txt = re.sub(r"\d+", str(v), p.text, count=1)
                full_w = R.ty.width(p.text, p.kind, p.size)
                im, pad = R.ty.img(txt, p.kind, p.size, p.color)
                x = p.x + full_w / 2 - (im.width - 2 * pad) / 2 - pad
                f.alpha_composite(with_alpha(im, clamp((t - p.t) / 0.06)), (int(x), int(p.y - pad)))


class PhotoHookScene(StatementScene):
    def default_role(self, i):
        return "small" if i == 0 else "big"

    def palette(self, th):
        p = super().palette(th)
        p.update(fg=(255, 255, 255), muted=(225, 225, 225), accent_word=hexc(th["accent"]))
        return p

    def prepare(self, R):
        super().prepare(R)
        self.photo = cover(R.hook, (int(R.W * 1.1), int(R.H * 1.1)))
        yy, xx = np.mgrid[0:R.H, 0:R.W]
        r = np.sqrt(((xx - R.W / 2) / (R.W / 2)) ** 2 + ((yy - R.H / 2) / (R.H / 2)) ** 2)
        vig = np.clip(1 - 0.5 * np.clip(r - 0.4, 0, None) ** 1.5, 0, 1)
        self.vig = Image.merge("RGB", [Image.fromarray((vig * 255).astype(np.uint8))] * 3)

    def background(self, R, t):
        z = 1 + 0.08 * ease_io((t - self.start) / max(0.1, self.end - self.start + TD))
        hw, hh = self.photo.size
        vw, vh = hw / 1.1 / z, hh / 1.1 / z
        ph = self.photo.resize((R.W, R.H), Image.BILINEAR,
                               box=((hw - vw) / 2, (hh - vh) / 2, (hw + vw) / 2, (hh + vh) / 2))
        return ImageChops.multiply(ph, self.vig).convert("RGBA")


class ListScene(Scene):
    """Blur-Stapel: nur die aktive Zeile scharf, Stapel gleitet pro Beat eine Zeile hoch."""

    def __init__(self, spec, ad):
        super().__init__(spec, ad)
        self.lines = [Line(l, "list") for l in spec["items"]]

    def time(self, t0, pace):
        t = t0 + 0.1
        for l in self.lines:
            l.place(t)
            t += max(pace["beat"], l.dur + 0.3)
        self.end = t - 0.1
        return self.end

    def beats(self):
        return [l.start for l in self.lines]

    def prepare(self, R):
        ty, size = R.ty, int(R.U * 1.1)
        while True:
            widths = [ty.width(l.text, "bold", size) for l in self.lines]
            aw = ty.width("→", "bold", size)
            if max(widths) / 2 + aw * 1.4 <= R.max_w / 2 or size < 30:
                break
            size -= 2
        self.size, self.lh, self.widths = size, size * 1.32, widths
        self.layers = []
        for l in self.lines:
            words = [(tok, self.pal["accent_word"] if l.is_accent(tok) else self.pal["fg"]) for tok in l.tokens]
            space = ty.font("bold", size).getlength(" ") * 0.9
            ims = [ty.img(tok, "bold", size, c) for tok, c in words]
            w = sum(im.width - 2 * pad for im, pad in ims) + space * (len(ims) - 1)
            pad0 = ims[0][1]
            base = Image.new("RGBA", (int(w) + 2 * pad0 + 32, ims[0][0].height + 32), (0, 0, 0, 0))
            x = 16
            for im, pad in ims:
                base.alpha_composite(im, (int(x), 16))
                x += im.width - 2 * pad + space
            self.layers.append([base] + [base.filter(ImageFilter.GaussianBlur(r)) for r in range(1, 13)])
        self.arrow, self.apad = ty.img("→", "bold", size, self.pal["accent"])

    def draw(self, R, f, t):
        pos = -1.0
        for k, l in enumerate(self.lines):
            if t >= l.start:
                pos = (k - 1) + spring((t - l.start) / 0.45)
        fin = ease_out((t - self.start) / 0.3)
        for i, layers in enumerate(self.layers):
            d = clamp(abs(i - pos))
            sc = 1 - 0.08 * d
            im = layers[int(round(12 * d))]
            if sc < 0.999:
                im = im.resize((int(im.width * sc), int(im.height * sc)), Image.BICUBIC)
            im = with_alpha(im, (1 - 0.72 * d) * fin)
            y = R.cy + (i - pos) * self.lh
            f.alpha_composite(im, (int(R.cx - im.width / 2), int(y - im.height / 2)))
            if d < 1:
                ar = with_alpha(self.arrow, 1 - d)
                ax = R.cx - self.widths[i] * sc / 2 - self.size * 0.35 - ar.width + self.apad
                f.alpha_composite(ar, (int(ax), int(y - ar.height / 2)))


class ChecklistScene(ListScene):
    """Punkte erscheinen untereinander mit animiertem Haken, bleiben stehen."""

    def prepare(self, R):
        ty, size = R.ty, int(R.U * 0.95)
        while max(ty.width(l.text, "bold", size) for l in self.lines) + size * 1.2 > R.max_w and size > 30:
            size -= 2
        self.size, self.lh = size, size * 1.55
        maxw = max(ty.width(l.text, "bold", size) for l in self.lines)
        self.x0 = R.cx - (maxw + size * 1.2) / 2
        self.y0 = R.cy - self.lh * (len(self.lines) - 1) / 2
        self.placed = []
        for i, l in enumerate(self.lines):
            y = self.y0 + i * self.lh
            x = self.x0 + size * 1.2
            space = ty.font("bold", size).getlength(" ") * 0.9
            asc, desc = ty.font("bold", size).getmetrics()
            row = []
            for tok, tm in zip(l.tokens, l.word_t):
                c = self.pal["accent_word"] if l.is_accent(tok) else self.pal["fg"]
                row.append(Placed(x, y - (asc + desc) / 2, tok, "bold", size, c, tm))
                x += ty.width(tok, "bold", size) + space
            self.placed.append(row)

    def draw(self, R, f, t):
        d = ImageDraw.Draw(f)
        s = self.size
        for i, l in enumerate(self.lines):
            if t < l.start:
                continue
            y = self.y0 + i * self.lh
            cx, cy = self.x0 + s * 0.4, y
            r = s * 0.42
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=self.pal["accent"])
            p = ease_out((t - l.start) / 0.3)
            pts = [(cx - r * 0.45, cy + r * 0.02), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.35)]
            on = self.pal["bg"]
            if p > 0:
                k1 = min(1, p * 2)
                d.line([pts[0], (pts[0][0] + (pts[1][0] - pts[0][0]) * k1, pts[0][1] + (pts[1][1] - pts[0][1]) * k1)],
                       fill=on, width=max(3, int(s * 0.09)))
                if p > 0.5:
                    k2 = (p - 0.5) * 2
                    d.line([pts[1], (pts[1][0] + (pts[2][0] - pts[1][0]) * k2, pts[1][1] + (pts[2][1] - pts[1][1]) * k2)],
                           fill=on, width=max(3, int(s * 0.09)))
            draw_words(R.ty, f, self.placed[i], t)


class PunchScene(Scene):
    """Jedes Wort einzeln bildschirmfuellend, Hintergrund wechselt pro Wort."""

    def default_role(self, i):
        return "punch"

    def prepare(self, R):
        self.words = []
        for l in self.lines:
            for tok, tm in zip(l.tokens, l.word_t):
                self.words.append((tok, tm, l.is_accent(tok)))
        self.sizes = {}
        for tok, _, _ in self.words:
            size = int(R.U * 3.2)
            while R.ty.width(tok, "bold", size) > R.max_w and size > 30:
                size -= 4
            self.sizes[tok] = size

    def beats(self):
        return [tm for l in self.lines for tm in l.word_t]

    def current(self, t):
        cur = None
        for i, (tok, tm, acc) in enumerate(self.words):
            if t >= tm:
                cur = i
        return cur

    def background(self, R, t):
        i = self.current(t)
        flip = i is not None and i % 2 == 1
        c = self.pal["accent"] if flip else self.pal["bgc"]
        return Image.new("RGBA", (R.W, R.H), c + (255,))

    def draw(self, R, f, t):
        i = self.current(t)
        if i is None:
            return
        tok, tm, acc = self.words[i]
        flip = i % 2 == 1
        color = self.pal["bgc"] if flip else (self.pal["accent"] if acc else self.pal["fg"])
        size = self.sizes[tok]
        asc, desc = R.ty.font("bold", size).getmetrics()
        p = Placed(R.cx - R.ty.width(tok, "bold", size) / 2, R.cy - (asc + desc) / 2, tok, "bold", size, color, tm)
        draw_words(R.ty, f, [p], t, pop=0.85)


class SplitScene(Scene):
    """Vorher (gedaempft, durchgestrichen) vs. Nachher (Akzentflaeche, faehrt ein)."""

    def __init__(self, spec, ad):
        super().__init__(spec, ad)
        self.lines = [Line(spec["before"], "before"), Line(spec["after"], "after")]

    def prepare(self, R):
        self.vertical = R.H > R.W
        if self.vertical:
            self.boxes = [(0, 0, R.W, R.H // 2), (0, R.H // 2, R.W, R.H)]
        else:
            self.boxes = [(0, 0, R.W // 2, R.H), (R.W // 2, 0, R.W, R.H)]
        self.placed = []
        for l, (x0, y0, x1, y1) in zip(self.lines, self.boxes):
            mw = (x1 - x0) * 0.8
            pal = dict(self.pal, accent_word=self.pal["fg"] if l.role == "after" else self.pal["accent"])
            self.placed.append(layout(R.ty, [(l, l.role)], (x0 + x1) / 2, (y0 + y1) / 2, mw, R.U, pal))

    def background(self, R, t):
        im = Image.new("RGBA", (R.W, R.H), mix(self.pal["bgc"], self.pal["fg"], 0.07) + (255,))
        return im

    def draw(self, R, f, t):
        before, after = self.lines
        draw_words(R.ty, f, self.placed[0], t)
        if self.placed[0] and t > before.start + before.dur:  # Durchstreichen
            k = ease_out((t - before.start - before.dur) / 0.3)
            d = ImageDraw.Draw(f)
            rows = {}
            for p in self.placed[0]:
                rows.setdefault(round(p.y), []).append(p)
            for y, ps in rows.items():
                x0 = ps[0].x
                x1 = ps[-1].x + R.ty.width(ps[-1].text, ps[-1].kind, ps[-1].size)
                asc, desc = R.ty.font(ps[0].kind, ps[0].size).getmetrics()
                yy = y + asc * 0.62
                d.line([(x0, yy), (x0 + (x1 - x0) * k, yy)], fill=self.pal["accent"], width=max(4, ps[0].size // 12))
        if t >= after.start - 0.25:
            k = ease_out((t - after.start + 0.25) / 0.45)
            x0, y0, x1, y1 = self.boxes[1]
            panel = Image.new("RGBA", (R.W, R.H), (0, 0, 0, 0))
            ImageDraw.Draw(panel).rectangle([x0, y0, x1, y1], fill=self.pal["accent"])
            draw_words(R.ty, panel, self.placed[1], t)
            off = (1 - k) * (R.H - y0 if self.vertical else R.W - x0)
            f.alpha_composite(panel, (0, int(off)) if self.vertical else (int(off), 0))


class PayoffScene(Scene):
    """Kurzer Payoff-Satz + Produktkarte mit 3D-Kippung."""

    def default_role(self, i):
        return "big" if len(self.spec.get("lines", [])) == 1 else ["grey", "big"][min(i, 1)]

    def prepare(self, R):
        if R.W > R.H:
            cx, cy, mw, ch = R.W * 0.34, R.H / 2, R.W * 0.42, int(R.H * 0.8)
            self.cc = (R.W * 0.73, R.H / 2)
        else:
            cx, cy, mw, ch = R.cx, R.H * 0.25, R.max_w, int(R.H * 0.52)
            self.cc = (R.W / 2, R.H * 0.62)
        U = R.U * (1.4 if len(self.lines) == 1 else 1.1)
        # Hochformat: Textblock muss zwischen oberen Rand und Karte passen, sonst verkleinern
        avail = (self.cc[1] - ch / 2 - R.H * 0.14) if R.H > R.W else R.H * 0.8
        if R.H > R.W:
            cy = R.H * 0.12 + avail / 2
        while True:
            self.placed = layout(R.ty, [(l, l.role) for l in self.lines], cx, cy, mw, U, self.pal)
            top = min(p.y for p in self.placed)
            bot = max(p.y + sum(R.ty.font(p.kind, p.size).getmetrics()) for p in self.placed)
            if bot - top <= avail or U < 40:
                break
            U *= 0.94
        cw = int(R.card.width * ch / R.card.height)
        self.card = R.card.resize((cw, ch), Image.LANCZOS)
        sh = Image.new("RGBA", (cw + 160, ch + 160), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([80, 100, 80 + cw, 100 + ch], int(cw * 0.13), fill=(0, 0, 0, 70))
        self.shadow = sh.filter(ImageFilter.GaussianBlur(28))

    def time(self, t0, pace):
        super().time(t0, pace)
        self.end = max(self.end, t0 + 1.5)  # Karte braucht Zeit zum Einfahren
        return self.end

    def hit_time(self):
        for l in self.lines:
            for tok, tm in zip(l.tokens, l.word_t):
                if l.is_accent(tok):
                    return tm
        return self.lines[-1].word_t[-1]

    def draw(self, R, f, t):
        draw_words(R.ty, f, self.placed, t)
        p = (t - self.start - 0.15) / 0.6
        if p <= 0:
            return
        slide = ease_out(p)
        angle = 24 * (1 - ease_out((t - self.start - 0.15) / 0.8))
        card = tilt(self.card, angle)
        cx, cy = self.cc
        off = (1 - slide) * R.W * 0.7
        f.alpha_composite(self.shadow, (int(cx + off - self.card.width / 2 - 80), int(cy - self.card.height / 2 - 80)))
        f.alpha_composite(card, (int(cx + off - card.width / 2), int(cy - card.height / 2)))


class CtaScene(Scene):
    """CTA (Karaoke), dann Endkarte: Preiszeile (gesprochen) + Marke/URL (Akzent auf Endung)."""

    def __init__(self, spec, ad):
        super().__init__(spec, ad)
        self.cta = Line(spec["cta"], "cta")
        self.price = Line(spec["price"], "price") if spec.get("price") else None
        self.brand, self.brand_end = spec.get("brand", "MARKE"), spec.get("brand_end", ".de")
        self.lines = [self.cta] + ([self.price] if self.price else [])

    def time(self, t0, pace):
        t = self.cta.place(t0)
        self.endcard = t + 0.25
        t = self.endcard + 0.15
        if self.price:
            t = self.price.place(t)
        self.brand_t = self.endcard + 0.4
        self.end = max(t, self.brand_t) + 1.1
        return self.end

    def prepare(self, R):
        self.cta_p = layout(R.ty, [(self.cta, "cta")], R.cx, R.cy, R.max_w, R.U, self.pal)
        self.price_p = layout(R.ty, [(self.price, "price")], R.cx, R.cy - R.U * 0.75, R.max_w, R.U,
                              self.pal) if self.price else []
        size = int(R.U * 1.4)
        full = self.brand + self.brand_end
        while R.ty.width(full, "bold", size) > R.max_w and size > 30:
            size -= 2
        asc, desc = R.ty.font("bold", size).getmetrics()
        bw = R.ty.width(self.brand, "bold", size)
        x = R.cx - R.ty.width(full, "bold", size) / 2
        y = R.cy + R.U * 0.35 - (asc + desc) / 2
        self.brand_p = [Placed(x, y, self.brand, "bold", size, self.pal["fg"], self.brand_t),
                        Placed(x + bw, y, self.brand_end, "bold", size, self.pal["accent"], self.brand_t)]

    def draw(self, R, f, t):
        draw_words(R.ty, f, self.cta_p, t, alpha=1 - clamp((t - self.endcard) / 0.2))
        if t >= self.endcard:
            draw_words(R.ty, f, self.price_p, t)
            draw_words(R.ty, f, self.brand_p, t)


SCENES = {"photo_hook": PhotoHookScene, "statement": StatementScene, "blur_list": ListScene,
          "checklist": ChecklistScene, "punch": PunchScene, "split": SplitScene,
          "payoff_card": PayoffScene, "cta_end": CtaScene}


def tilt(card, angle):
    if abs(angle) < 0.05:
        return card
    w, h = card.size
    k = math.sin(math.radians(angle)) * 0.22
    nw = w * math.cos(math.radians(angle))
    pad = int(h * k) + 2
    dst = [(0, pad - h * k), (nw, pad + h * k), (nw, pad + h - h * k), (0, pad + h + h * k)]
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    m = []
    for (x, y), (u, v) in zip(dst, src):
        m += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
    coeffs = np.linalg.solve(np.array(m, float), np.array([c for p in src for c in p], float)).tolist()
    return card.transform((int(nw) + 2, h + 2 * pad), Image.PERSPECTIVE, coeffs, Image.BICUBIC)


# ------------------------------------------------------------------ Ad (Timeline + Audio)
class Ad:
    def __init__(self, spec):
        self.spec = spec
        self.theme = THEMES[spec["theme"]] if isinstance(spec["theme"], str) else spec["theme"]
        self.fontset = FONTSETS[spec.get("font", "intertight")]
        self.pace = PACING[spec.get("pacing", "normal")]
        self.scenes = [SCENES[s["type"]](s, self) for s in spec["scenes"]]
        for sc in self.scenes:
            sc.pal = sc.palette(self.theme)
            for l in sc.all_lines():
                l.synth(self.pace["rate"], spec.get("pitch", 48))
        t = 0.25
        for i, sc in enumerate(self.scenes):
            sc.start = t if i == 0 else t
            lead = 0.05 if i == 0 else (sc.lead_cut if sc.transition == "cut" else TD + 0.05)
            t = sc.time(t + lead, self.pace)
        self.total = t

    def warnings(self):
        w = []
        if not 14.5 <= self.total <= 20.5:
            w.append(f"Laenge {self.total:.1f} s liegt ausserhalb 15-20 s.")
        for sc in self.scenes:
            for l in sc.all_lines():
                if "TODO" in l.text:
                    w.append(f"Platzhalter-Text in Szene {sc.type}: {l.text}")
                if len(l.tokens) > 8 and sc.type not in ("statement",):
                    w.append(f"Zeile mit {len(l.tokens)} Woertern ist lang: '{l.text}'")
        first = self.scenes[0]
        if first.lines and first.lines[0].start > 1.0:
            w.append("Erstes Wort kommt erst nach 1 s - Hook schneller machen.")
        return w

    def build_audio(self, path):
        n = int((self.total + 0.5) * SR)
        mixb = np.zeros(n, dtype=np.float32)

        def put(sig, at):
            i = int(at * SR)
            if i < 0 or i >= n:
                return
            mixb[i:i + len(sig)] += sig[: n - i]

        rng = np.random.default_rng(1)
        tt = np.arange(int(0.05 * SR)) / SR
        tick = (np.sin(2 * np.pi * 1900 * tt) * 0.6 + rng.normal(0, 0.15, tt.size)) * np.exp(-tt / 0.008) * 0.35
        tw = np.arange(int(0.35 * SR)) / SR
        noise = rng.normal(0, 1, tw.size)
        whoosh = np.convolve(noise, np.ones(30) / 30, "same") * np.sin(np.pi * tw / tw[-1]) ** 2 * 0.25
        for sc in self.scenes:
            for l in sc.all_lines():
                put(l.audio, l.start)
            for b in sc.beats():
                put(tick, b)
            if sc.transition in ("slide", "zoom", "wipe_up", "flash", "blur_wipe"):
                put(whoosh, sc.start)
            if isinstance(sc, PayoffScene):
                hit_t = sc.hit_time()
                dur = 0.9
                m = int(dur * SR)
                tr = np.arange(m) / SR
                y, out, nz = 0.0, np.zeros(m), rng.normal(0, 1, m)
                for i in range(m):
                    y += (0.02 + 0.5 * (i / m) ** 2) * (nz[i] - y)
                    out[i] = y
                tone = np.sin(2 * np.pi * np.cumsum(220 + 660 * (tr / dur) ** 2) / SR) * 0.25
                put(((out * 0.5 + tone) * (tr / dur) ** 2.2 * 0.35).astype(np.float32), hit_t - dur)
                th = np.arange(int(0.7 * SR)) / SR
                body = np.sin(2 * np.pi * np.cumsum(45 + 70 * np.exp(-th / 0.04)) / SR) * np.exp(-th / 0.18)
                put(((body + rng.normal(0, 1, th.size) * np.exp(-th / 0.01) * 0.3) * 0.6).astype(np.float32), hit_t)
        raw = TMP / f"{self.spec['id']}_mix_raw.wav"
        with wave.open(str(raw), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((np.clip(mixb / max(1.0, np.abs(mixb).max()), -1, 1) * 32767).astype(np.int16).tobytes())
        res = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af",
                              "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        m = json.loads(res[res.rindex("{"):])
        af = ("loudnorm=I=-14:TP=-1:LRA=11:linear=true:"
              f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
              f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af", af, "-ar", str(SR), "-ac", "2",
                        str(path)], check=True)


# ------------------------------------------------------------------ Renderer pro Format
class Renderer:
    def __init__(self, ad, fmt, hook, card):
        self.ad, self.fmt = ad, fmt
        self.W, self.H = (1920, 1080) if fmt == "16x9" else (1080, 1920)
        mx, my = (0.10, 0.12) if fmt == "9x16" else (0.08, 0.10)
        self.max_w = self.W * (1 - 2 * mx)
        self.cx, self.cy = self.W / 2, self.H / 2
        self.U = 100 if fmt == "9x16" else 124
        self.ty = Typo(ad.fontset)
        self.hook, self.card = hook, card
        for sc in ad.scenes:
            sc.prepare(self)
        self._last = {}

    def scene_frame(self, i, t):
        sc = self.ad.scenes[i]
        f = sc.background(self, t)
        sc.draw(self, f, t)
        return f

    def frame(self, t):
        sc_list = self.ad.scenes
        i = max(k for k, sc in enumerate(sc_list) if sc.start <= t or k == 0)
        sc = sc_list[i]
        cur = self.scene_frame(i, t)
        p = (t - sc.start) / TD
        if i > 0 and sc.transition != "cut" and p < 1:
            if i not in self._last:
                prev = sc_list[i - 1]
                self._last[i] = self.scene_frame(i - 1, prev.end - 1e-3)
            cur = self.transition(sc.transition, self._last[i], cur, clamp(p), sc.pal["bgc"])
        return cur.convert("RGB")

    def transition(self, kind, a, b, p, bgc):
        W, H = self.W, self.H
        e = ease_io(p)
        if kind == "slide":
            out = Image.new("RGBA", (W, H))
            out.paste(a, (int(-W * e), 0))
            out.paste(b, (int(W * (1 - e)), 0))
            return out
        if kind == "zoom":
            s = 1 + 0.25 * e
            za = a.resize((int(W * s), int(H * s)), Image.BILINEAR).crop(
                (int(W * (s - 1) / 2), int(H * (s - 1) / 2), int(W * (s - 1) / 2) + W, int(H * (s - 1) / 2) + H))
            return Image.blend(za, b, e)
        if kind == "flash":
            white = Image.new("RGBA", (W, H), (255, 255, 255, 255))
            return Image.blend(a, white, p * 2) if p < 0.5 else Image.blend(white, b, (p - 0.5) * 2)
        if kind in ("blur_wipe", "wipe_up"):
            src = a.filter(ImageFilter.GaussianBlur(40 * e)) if kind == "blur_wipe" else a
            soft = (0.35 if kind == "blur_wipe" else 0.04) * H
            edge = H + soft - e * (H + 2 * soft)
            g = np.clip((np.arange(H) - edge) / soft + 0.5, 0, 1)
            mask = Image.fromarray((np.repeat(g[:, None], W, 1) * 255).astype(np.uint8))
            out = src.copy()
            out.paste(b, (0, 0), mask)
            return out
        return b


_R = None


def _init(spec_path, fmt):
    global _R
    spec = json.loads(Path(spec_path).read_text())
    ad = Ad(spec)
    hook, card = load_assets(spec, hexc(ad.theme["accent"]))
    _R = Renderer(ad, fmt, hook, card)


def _frame(i):
    return _R.frame(i / FPS).tobytes()


def render(spec_path, ad, fmt, audio):
    OUT.mkdir(exist_ok=True)
    W, H = (1920, 1080) if fmt == "16x9" else (1080, 1920)
    path = OUT / f"{ad.spec['id']}_{fmt}.mp4"
    n = int(ad.total * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
           "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(4, initializer=_init, initargs=(str(spec_path), fmt)) as pool:
        for buf in pool.imap(_frame, range(n), chunksize=6):
            proc.stdin.write(buf)
    proc.stdin.close()
    proc.wait()
    print("fertig:", path)
    return path


def preview(ad, spec, fmt):
    hook, card = load_assets(spec, hexc(ad.theme["accent"]))
    R = Renderer(ad, fmt, hook, card)
    times = []
    for sc in ad.scenes:
        times += [sc.start + (sc.end - sc.start) * 0.45, sc.end - 0.05]
    tw, th = (384, 216) if fmt == "16x9" else (216, 384)
    cols = 6
    rows = math.ceil(len(times) / cols)
    sheet = Image.new("RGB", (cols * (tw + 6), rows * (th + 6)), (255, 0, 255))
    for k, t in enumerate(times):
        sheet.paste(R.frame(t).resize((tw, th)), ((k % cols) * (tw + 6), (k // cols) * (th + 6)))
    OUT.mkdir(exist_ok=True)
    p = OUT / f"{spec['id']}_preview_{fmt}.png"
    sheet.save(p)
    print("Vorschau:", p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--formats", nargs="*")
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text())
    ad = Ad(spec)
    print(f"{spec['id']}: {ad.total:.2f} s")
    for sc in ad.scenes:
        print(f"  {sc.start:6.2f}-{sc.end:6.2f}  {sc.type:12s} {sc.transition:9s} "
              + " | ".join(l.text for l in sc.all_lines()))
    for w in ad.warnings():
        print("  WARNUNG:", w)
    fmts = a.formats or spec.get("formats", ["9x16", "16x9"])
    if a.check:
        return
    if a.preview:
        for fmt in fmts:
            preview(ad, spec, fmt)
        return
    audio = TMP / f"{spec['id']}_mix.wav"
    ad.build_audio(audio)
    for fmt in fmts:
        render(a.spec, ad, fmt, audio)


if __name__ == "__main__":
    main()
