"""Erzeugt zwei kurze Erklaervideos (MP4) mit Pillow + ffmpeg.

Aufruf: python3 videos/make_videos.py
"""
import colorsys
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 24
OUT = Path(__file__).parent
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT, size)


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def seg(t, a, b):
    """Fortschritt 0..1 von t im Intervall [a, b]."""
    return ease((t - a) / (b - a))


def mix(c1, c2, k):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * k) for i in range(3))


def gradient(top, bottom):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=mix(top, bottom, y / H))
    return img


def text(d, xy, s, size, fill=(255, 255, 255), bold=False, anchor="mm", alpha=1.0, bg=None):
    if alpha <= 0:
        return
    col = fill if bg is None else mix(bg, fill, alpha)
    d.text(xy, s, font=font(size, bold), fill=col, anchor=anchor)


def caption(d, s, alpha=1.0, bg=(20, 24, 40)):
    text(d, (W // 2, H - 60), s, 34, (240, 240, 250), alpha=alpha, bg=bg)


# ---------------------------------------------------------------- Video 1
SKY_TOP, SKY_BOT = (18, 40, 90), (70, 130, 200)


def sky_title(t, img):
    d = ImageDraw.Draw(img)
    a = seg(t, 0.0, 0.25)
    text(d, (W // 2, 280), "Warum ist der Himmel blau?", 66, bold=True, alpha=a, bg=SKY_TOP)
    text(d, (W // 2, 370), "Eine Erklaerung in 40 Sekunden", 34, (200, 220, 255), alpha=seg(t, 0.3, 0.6), bg=SKY_TOP)
    sun_r = 40 + 6 * math.sin(t * 12)
    d.ellipse([W // 2 - sun_r, 500 - sun_r, W // 2 + sun_r, 500 + sun_r], fill=(255, 220, 90))


def sky_white(t, img):
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 90), "Sonnenlicht sieht weiss aus ...", 46, bold=True)
    # Strahl, der sich in Regenbogenfarben auffaechert
    x0, y0 = 220, 360
    d.ellipse([x0 - 70, y0 - 70, x0 + 70, y0 + 70], fill=(255, 220, 90))
    p = seg(t, 0.15, 0.6)
    d.line([(x0 + 70, y0), (560, y0)], fill=(255, 255, 255), width=10)
    d.polygon([(560, y0 - 50), (560, y0 + 50), (700, y0)], outline=(255, 255, 255), fill=(110, 150, 210))
    for i in range(7):
        hue = 0.0 + (0.75 * i / 6)
        r, g, b = colorsys.hsv_to_rgb(hue, 1, 1)
        ang = math.radians(-24 + i * 8)
        L = 520 * p
        d.line([(700, y0), (700 + L * math.cos(ang), y0 + L * math.sin(ang))],
               fill=(int(r * 255), int(g * 255), int(b * 255)), width=9)
    caption(d, "... enthaelt aber alle Farben des Regenbogens.", seg(t, 0.55, 0.8), bg=SKY_BOT)


def sky_scatter(t, img):
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 80), "Luftmolekuele streuen das Licht", 46, bold=True)
    mols = [(520, 360), (700, 250), (860, 440), (640, 500), (950, 300)]
    for mx, my in mols:
        d.ellipse([mx - 16, my - 16, mx + 16, my + 16], fill=(230, 235, 245))
    # rotes Licht (geradeaus) und blaues Licht (wird gestreut)
    p = seg(t, 0.1, 0.7)
    y = 360
    xr = 120 + (W - 240) * p
    d.line([(120, y), (xr, y)], fill=(255, 80, 60), width=8)
    d.ellipse([xr - 12, y - 12, xr + 12, y + 12], fill=(255, 80, 60))
    xb = min(xr, 520)
    d.line([(120, y + 30), (xb, y + 30)], fill=(70, 140, 255), width=8)
    if xr > 520:
        q = seg(t, 0.35, 0.8)
        for k, ang in enumerate([-60, -20, 25, 70, 110, 150, 200, 250]):
            a = math.radians(ang)
            L = 260 * q
            d.line([(520, 360), (520 + L * math.cos(a), 360 + L * math.sin(a))], fill=(70, 140, 255), width=6)
    caption(d, "Blaues Licht wird viel staerker gestreut als rotes.", seg(t, 0.6, 0.85), bg=SKY_BOT)


def sky_blue(t, img):
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 90), "Das gestreute Blau kommt aus allen Richtungen", 42, bold=True)
    # Himmel-Kuppel als Halbkreis mit Blau-Punkten
    cx, cy = W // 2, 560
    d.pieslice([cx - 420, cy - 420, cx + 420, cy + 420], 180, 360, fill=(40, 100, 190))
    n = int(120 * seg(t, 0.1, 0.8))
    for i in range(n):
        a = math.radians(180 + (i * 137.5) % 180)
        r = 60 + (i * 53) % 340
        px, py = cx + r * math.cos(a), cy + r * math.sin(a)
        d.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(150, 200, 255))
    d.rectangle([0, cy, W, H], fill=(60, 120, 60))
    d.ellipse([cx - 28, cy - 28, cx + 28, cy + 28], fill=(255, 220, 90))
    caption(d, "Darum sehen wir tagsueber einen blauen Himmel.", seg(t, 0.6, 0.85), bg=(60, 120, 60))


def sky_sunset(t, img):
    img.paste(gradient(mix((30, 30, 80), (230, 110, 50), seg(t, 0, 0.8)), (250, 190, 90)))
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 90), "Und warum ist der Sonnenuntergang rot?", 46, bold=True)
    sy = 330 + 160 * seg(t, 0, 1)
    d.ellipse([W // 2 - 60, sy - 60, W // 2 + 60, sy + 60], fill=(255, 120, 40))
    d.rectangle([0, 560, W, H], fill=(30, 35, 55))
    text(d, (W // 2, 620), "Abends ist der Weg durch die Luft lang: Blau geht verloren, Rot bleibt.", 28,
         (255, 235, 210), alpha=seg(t, 0.4, 0.7), bg=(30, 35, 55))


def video_sky():
    scenes = [(4.5, sky_title), (7, sky_white), (8, sky_scatter), (7, sky_blue), (7, sky_sunset)]
    render(scenes, OUT / "video1_himmel_blau.mp4", SKY_TOP, SKY_BOT)


# ---------------------------------------------------------------- Video 2
GIT_TOP, GIT_BOT = (22, 24, 38), (34, 38, 60)
ORANGE, GREEN, BLUE = (240, 120, 60), (90, 200, 120), (90, 150, 240)


def commit(d, x, y, col, label, alpha=1.0):
    r = int(26 * alpha)
    if r <= 0:
        return
    d.ellipse([x - r, y - r, x + r, y + r], fill=col, outline=(255, 255, 255), width=3)
    if alpha > 0.6:
        text(d, (x, y + 52), label, 22, (210, 215, 230))


def git_title(t, img):
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 280), "Wie funktioniert Git?", 70, bold=True, alpha=seg(t, 0, 0.25), bg=GIT_TOP)
    text(d, (W // 2, 370), "Versionsverwaltung in einfachen Schritten", 34, (180, 190, 220),
         alpha=seg(t, 0.3, 0.6), bg=GIT_TOP)
    for i in range(5):
        commit(d, 340 + i * 150, 500, ORANGE, "", seg(t, 0.4 + i * 0.1, 0.6 + i * 0.1))
        if i:
            d.line([(340 + (i - 1) * 150 + 26, 500), (340 + i * 150 - 26, 500)], fill=(255, 255, 255), width=3)


def git_commits(t, img):
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 90), "1. Commits sind Schnappschuesse deines Projekts", 42, bold=True)
    labels = ["Start", "Login", "Design", "Bugfix"]
    for i, lab in enumerate(labels):
        a = seg(t, 0.1 + i * 0.18, 0.28 + i * 0.18)
        x = 260 + i * 250
        if i:
            d.line([(x - 250 + 26, 360), (x - 26, 360)], fill=(255, 255, 255), width=4)
        commit(d, x, 360, ORANGE, lab, a)
    caption(d, "Jeder Commit merkt sich den Stand - du kannst jederzeit zurueck.", seg(t, 0.75, 0.95), bg=GIT_BOT)


def git_branch(t, img):
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 90), "2. Branches: gefahrlos Neues ausprobieren", 42, bold=True)
    main = [(260, 440), (460, 440), (660, 440), (1000, 440)]
    for i in range(len(main) - 1):
        d.line([(main[i][0], 440), (main[i + 1][0], 440)], fill=(255, 255, 255), width=4)
    for i, (x, y) in enumerate(main):
        commit(d, x, y, ORANGE, ["Start", "Login", "Design", "Bugfix"][i])
    text(d, (260, 550), "main", 26, ORANGE, bold=True, anchor="mm")
    # Feature-Branch
    p = seg(t, 0.15, 0.7)
    pts = [(460, 440), (560, 270), (760, 270)]
    if p > 0:
        d.line([pts[0], pts[1]], fill=(255, 255, 255), width=4)
        d.line([pts[1], (pts[1][0] + 200 * min(1, p * 1.5), 270)], fill=(255, 255, 255), width=4)
        commit(d, 560, 270, GREEN, "Idee", seg(t, 0.15, 0.35))
        commit(d, 760, 270, GREEN, "Test", seg(t, 0.4, 0.6))
        text(d, (660, 205), "feature", 26, GREEN, bold=True)
    for i, (x, y) in enumerate(main):  # Knoten ueber die Linien zeichnen
        commit(d, x, y, ORANGE, ["Start", "Login", "Design", "Bugfix"][i])
    caption(d, "Dein Hauptzweig bleibt unberuehrt, bis die Idee fertig ist.", seg(t, 0.75, 0.95), bg=GIT_BOT)


def git_merge(t, img):
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 90), "3. Merge: Aenderungen zusammenfuehren", 42, bold=True)
    d.line([(260, 440), (1000, 440)], fill=(255, 255, 255), width=4)
    for x, lab in zip((260, 460, 660), ("Start", "Login", "Design")):
        commit(d, x, 440, ORANGE, lab)
    d.line([(460, 440), (560, 270), (760, 270)], fill=(255, 255, 255), width=4)
    commit(d, 560, 270, GREEN, "Idee")
    commit(d, 760, 270, GREEN, "Test")
    p = seg(t, 0.2, 0.7)
    mx, my = 760 + (1000 - 760) * p, 270 + (440 - 270) * p
    d.line([(760, 270), (mx, my)], fill=BLUE, width=5)
    commit(d, 1000, 440, BLUE, "Merge", seg(t, 0.65, 0.85))
    for x, lab in zip((460, 660), ("Login", "Design")):  # Knoten ueber die Linien zeichnen
        commit(d, x, 440, ORANGE, lab)
    commit(d, 760, 270, GREEN, "Test")
    caption(d, "Der Merge vereint beide Zweige zu einem gemeinsamen Stand.", seg(t, 0.8, 0.97), bg=GIT_BOT)


def git_remote(t, img):
    d = ImageDraw.Draw(img)
    text(d, (W // 2, 90), "4. GitHub: dein Projekt in der Cloud", 42, bold=True)
    d.rounded_rectangle([140, 260, 480, 460], 24, outline=(255, 255, 255), width=4)
    text(d, (310, 330), "Dein Rechner", 34, bold=True)
    text(d, (310, 390), "lokales Repo", 26, (180, 190, 220))
    d.rounded_rectangle([800, 260, 1140, 460], 24, outline=BLUE, width=4)
    text(d, (970, 330), "GitHub", 34, bold=True)
    text(d, (970, 390), "Remote-Repo", 26, (180, 190, 220))
    for k, (label, y, direction) in enumerate((("git push", 310, 1), ("git pull", 420, -1))):
        a = seg(t, 0.15 + k * 0.3, 0.45 + k * 0.3)
        x1, x2 = (490, 790) if direction == 1 else (790, 490)
        x = x1 + (x2 - x1) * a
        d.line([(x1, y), (x, y)], fill=GREEN if direction == 1 else ORANGE, width=6)
        d.ellipse([x - 12, y - 12, x + 12, y + 12], fill=GREEN if direction == 1 else ORANGE)
        text(d, (640, y - 28), label, 26, bold=True, alpha=a, bg=GIT_BOT)
    caption(d, "Push schickt deine Commits hoch, Pull holt die der anderen.", seg(t, 0.8, 0.97), bg=GIT_BOT)


def video_git():
    scenes = [(5, git_title), (8, git_commits), (9, git_branch), (8, git_merge), (8, git_remote)]
    render(scenes, OUT / "video2_git_erklaert.mp4", GIT_TOP, GIT_BOT)


# ---------------------------------------------------------------- Rendering
def render(scenes, path, top, bottom):
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart", str(path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    base = gradient(top, bottom)
    fade = int(0.4 * FPS)
    for dur, fn in scenes:
        n = int(dur * FPS)
        for f in range(n):
            img = base.copy()
            fn(f / (n - 1), img)
            # weiches Ein-/Ausblenden zwischen den Szenen
            k = min(f, n - 1 - f) / fade
            if k < 1:
                img = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), img, ease(k))
            proc.stdin.write(img.tobytes())
    proc.stdin.close()
    proc.wait()
    print("fertig:", path)


if __name__ == "__main__":
    video_sky()
    video_git()
