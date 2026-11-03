"""Erzeugt ein neues, noch nie verwendetes Kreativ-Briefing (Prompt) + Spec-Geruest.

  python3 brief.py                 neues Briefing -> briefs/ad_XXX.md + specs/ad_XXX.json (Texte = TODO)
  python3 brief.py --seed 42       reproduzierbar
  python3 brief.py --list          bisherige Kombinationen anzeigen

Variationsregeln: Gegenueber jedem der letzten 5 Ads muessen sich mindestens 4 der Dimensionen
(hook, body, theme, font, angle, pacing, transitions) unterscheiden, und die Gesamtkombination
darf nie doppelt vorkommen. Verwendete Kombinationen stehen in history.json.
"""
import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).parent
P = json.loads((ROOT / "patterns.json").read_text())
PRODUCT = json.loads((ROOT / "product.json").read_text())
HIST = ROOT / "history.json"
DIMS = ["hook", "body", "theme", "font", "angle", "pacing", "transitions"]


def load_hist():
    return json.loads(HIST.read_text()) if HIST.exists() else []


def next_id(hist):
    nums = [int(h["id"].split("_")[1]) for h in hist] + [
        int(p.stem.split("_")[1]) for p in (ROOT / "specs").glob("ad_*.json")]
    return f"ad_{max(nums, default=0) + 1:03d}"


def choose(rng, items):
    """Gewichtete Auswahl: Muster koennen in patterns.json ein Feld "weight" haben (Standard 1)."""
    return rng.choices(items, weights=[x.get("weight", 1) for x in items])[0]


def pick(rng, hist):
    for _ in range(5000):
        hook = choose(rng, P["hooks"])
        bodies = [b for b in P["bodies"] if b["scene"] != hook["scene"]]
        body = choose(rng, bodies)
        turn = choose(rng, P["turns"])
        if body["scene"] == "punch" and turn["id"] == "none" and hook["scene"] == "punch":
            continue
        trans = rng.sample([t for t in P["transitions"] if t != "cut"], 2) + ["cut"]
        rng.shuffle(trans)
        c = {
            "hook": hook["id"], "turn": turn["id"], "body": body["id"],
            "payoff": choose(rng, P["payoffs"])["id"], "cta": choose(rng, P["ctas"])["id"],
            "angle": choose(rng, P["angles"])["id"], "theme": choose(rng, P["themes"])["id"],
            "font": choose(rng, P["fonts"])["id"], "pacing": choose(rng, P["pacing"])["id"],
            "transitions": "+".join(sorted(trans)),
        }
        key = "|".join(c[k] for k in sorted(c))
        if any(h.get("key") == key for h in hist):
            continue
        if any(sum(c[d] != h["combo"].get(d) for d in DIMS) < 4 for h in hist[-5:]):
            continue
        return c, key, trans
    raise SystemExit("Keine neue Kombination gefunden - patterns.json erweitern.")


def by_id(group, i):
    return next(x for x in P[group] if x["id"] == i)


def scene_skeleton(kind, pat, trans, bg=None):
    s = {"type": kind, "transition": trans}
    if bg:
        s["bg"] = bg
    if kind in ("blur_list", "checklist"):
        s["items"] = ["TODO Punkt 1", "TODO Punkt 2", "TODO Punkt 3"]
    elif kind == "split":
        s["before"] = "TODO vorher (Problem, max 5 Woerter)"
        s["after"] = {"text": "TODO nachher (Loesung, max 5 Woerter)", "accent": []}
    elif kind == "punch":
        s["lines"] = [{"text": "TODO Drei. Kurze. Worte.", "accent": []}]
    else:
        roles = pat.get("roles") or ["big"]
        s["lines"] = [{"text": f"TODO ({r})", "role": r, "accent": []} for r in roles]
    return s


def build(c, trans, new_id):
    hook, body, turn = by_id("hooks", c["hook"]), by_id("bodies", c["body"]), by_id("turns", c["turn"])
    tr = iter(trans * 3)
    scenes = []
    hs = scene_skeleton(hook["scene"], hook, "cut", hook.get("bg"))
    if hook["id"] == "stat_shock":
        hs["lines"] = [{"text": "TODO Zahl", "role": "number"}, {"text": "TODO Kontext", "role": "big", "accent": []}]
    elif hook["scene"] == "photo_hook":
        q = "?" if hook["id"] == "photo_question" else "."
        hs["lines"] = [{"text": "TODO Einstieg", "role": "small"},
                       {"text": f"TODO Problem (max 6 Woerter){q}", "role": "big", "accent": []}]
    scenes.append(hs)
    if turn["roles"]:
        scenes.append(scene_skeleton("statement", turn, next(tr)))
    bs = scene_skeleton(body["scene"], body, next(tr))
    if body["id"] == "stat_proof":
        bs["lines"] = [{"text": "TODO Zahl", "role": "number"}, {"text": "TODO Kontext", "role": "big", "accent": []}]
    scenes.append(bs)
    pay = {"type": "payoff_card", "transition": next(tr),
           "lines": [{"text": "TODO Payoff (2-3 Woerter)", "accent": []}] if c["payoff"] == "card" else
           [{"text": "TODO kleine Zeile", "role": "grey"}, {"text": "TODO grosse Zeile", "role": "big", "accent": []}]}
    scenes.append(pay)
    scenes.append({"type": "cta_end", "transition": next(tr), "cta": {"text": "TODO CTA", "accent": []},
                   "price": PRODUCT["price_line"], "brand": PRODUCT["brand"], "brand_end": PRODUCT["brand_end"]})
    return {"id": new_id, "formats": ["9x16", "16x9"], "theme": c["theme"], "font": c["font"], "pacing": c["pacing"],
            "patterns": c, "assets": {"hook": PRODUCT.get("hook_photo"), "screenshot": PRODUCT.get("screenshot"),
                                      "placeholder_seed": random.randint(1, 99)},
            "scenes": scenes}


def brief_md(c, spec):
    th = by_id("themes", c["theme"])
    lines = [f"# Briefing {spec['id']}", "",
             f"Kinetic-Typography-Video-Ad, 9:16 + 16:9, 60 fps, 15-20 s, Sprache Deutsch, fuer **{PRODUCT['name']}**.", "",
             "## Gewaehlte Muster", ""]
    for dim, group in [("hook", "hooks"), ("turn", "turns"), ("body", "bodies"), ("payoff", "payoffs"),
                       ("cta", "ctas"), ("angle", "angles")]:
        x = by_id(group, c[dim])
        why = f" - _{x['why']}_" if x.get("why") else ""
        lines.append(f"- **{dim}: {x['id']}** - {x['desc']}{why}")
    lines += [f"- **Farbwelt:** {th['id']} (bg {th['bg']}, Text {th['fg']}, Akzent {th['accent']})",
              f"- **Schrift:** {c['font']}", f"- **Tempo:** {c['pacing']}", f"- **Uebergaenge:** {c['transitions']}", "",
              "## Produktfakten (nur diese duerfen behauptet werden)", ""]
    lines += [f"- {f}" for f in PRODUCT["facts"]]
    lines += ["", "## Grundregeln", ""] + [f"- {r}" for r in P["principles"]]
    lines += ["", "## Szenenfolge", ""]
    for i, s in enumerate(spec["scenes"], 1):
        lines.append(f"{i}. `{s['type']}` (Uebergang: {s.get('transition', 'cut')}{', Hintergrund ' + s['bg'] if s.get('bg') else ''})")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    hist = load_hist()
    if a.list:
        for h in hist:
            print(h["id"], h["combo"])
        return
    rng = random.Random(a.seed)
    c, key, trans = pick(rng, hist)
    new_id = next_id(hist)
    spec = build(c, trans, new_id)
    (ROOT / "specs").mkdir(exist_ok=True)
    (ROOT / "briefs").mkdir(exist_ok=True)
    (ROOT / "specs" / f"{new_id}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    (ROOT / "briefs" / f"{new_id}.md").write_text(brief_md(c, spec))
    hist.append({"id": new_id, "key": key, "combo": c})
    HIST.write_text(json.dumps(hist, ensure_ascii=False, indent=2) + "\n")
    print(f"Neu: briefs/{new_id}.md und specs/{new_id}.json")
    print(json.dumps(c, ensure_ascii=False))


if __name__ == "__main__":
    main()
