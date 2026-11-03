"""Zerlegt eine Video-Ad (z. B. eine gut laufende Fremd- oder eigene Ad) in messbare Merkmale.

  python3 analyze_ad.py pfad/zur/ad.mp4 [--name kurzname]

Ergebnis in analysis/<name>/:
  report.json   Dauer, Format, Schnitte, Schnitte/s, mittlere Einstellungslaenge, Lautheit, Farben
  hook.png      Bilder bei 0.0 / 0.5 / 1.0 / 1.5 / 2.0 / 3.0 s (die entscheidenden ersten Sekunden)
  cuts.png      Ein Bild pro Einstellung (nach jedem Schnitt)
Die Bilder schaut sich der Agent danach an und traegt markante Muster in patterns.json ein.
"""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type,width,height,r_frame_rate", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    num, den = v["r_frame_rate"].split("/")
    return float(j["format"]["duration"]), v["width"], v["height"], float(num) / float(den), \
        any(s["codec_type"] == "audio" for s in j["streams"])


def cuts(path, thresh):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", f"select='gt(scene,{thresh})',showinfo",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", err)]


def frame_at(path, t, w):
    p = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                        "-vf", f"scale={w}:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    from io import BytesIO
    return Image.open(BytesIO(p.stdout)).convert("RGB") if p.stdout else None


def sheet(frames, labels, path, cols=6):
    frames = [f for f in frames if f]
    if not frames:
        return
    w, h = frames[0].size
    rows = math.ceil(len(frames) / cols)
    s = Image.new("RGB", (cols * (w + 6), rows * (h + 26)), (30, 30, 30))
    from PIL import ImageDraw
    d = ImageDraw.Draw(s)
    for i, (f, lab) in enumerate(zip(frames, labels)):
        x, y = (i % cols) * (w + 6), (i // cols) * (h + 26)
        s.paste(f.resize((w, h)), (x, y + 20))
        d.text((x + 4, y + 4), lab, fill=(255, 255, 255))
    s.save(path)


def loudness(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-map", "0:a?", "-af", "ebur128", "-f", "null",
                          "-"], capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    return float(m[-1]) if m else None


def palette(img, n=5):
    q = img.resize((120, 120)).quantize(n)
    pal = q.getpalette()[: n * 3]
    counts = sorted(q.getcolors(), reverse=True)
    return ["#%02X%02X%02X" % tuple(pal[i * 3:i * 3 + 3]) for _, i in counts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--name")
    ap.add_argument("--thresh", type=float, default=0.3)
    a = ap.parse_args()
    path = Path(a.video)
    name = a.name or path.stem
    out = ROOT / "analysis" / name
    out.mkdir(parents=True, exist_ok=True)
    dur, w, h, fps, has_audio = probe(path)
    cs = cuts(path, a.thresh)
    shots = [0.0] + cs
    lens = [b - a_ for a_, b in zip(shots, shots[1:] + [dur])]
    tw = 270 if h > w else 384
    hook_t = [t for t in (0, 0.5, 1, 1.5, 2, 3) if t < dur]
    sheet([frame_at(path, t, tw) for t in hook_t], [f"{t:.1f}s" for t in hook_t], out / "hook.png")
    shot_t = [min(dur - 0.05, s + 0.15) for s in shots][:36]
    sheet([frame_at(path, t, tw) for t in shot_t], [f"{t:.1f}s" for t in shot_t], out / "cuts.png")
    first = frame_at(path, min(0.5, dur / 2), 200)
    rep = {
        "datei": str(path), "dauer_s": round(dur, 2), "format": f"{w}x{h}", "seitenverhaeltnis": round(w / h, 3),
        "fps": round(fps, 2), "ton": has_audio, "schnitte": len(cs), "schnitte_pro_s": round(len(cs) / dur, 2),
        "mittlere_einstellung_s": round(sum(lens) / len(lens), 2), "erster_schnitt_s": round(cs[0], 2) if cs else None,
        "schnittzeiten": [round(c, 2) for c in cs], "lautheit_lufs": loudness(path) if has_audio else None,
        "farben_erstes_bild": palette(first) if first else [],
    }
    (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"Bilder: {out / 'hook.png'} und {out / 'cuts.png'}")


if __name__ == "__main__":
    main()
