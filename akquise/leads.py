"""Lead-Verwaltung fuer die Partner-Akquise (gemeinsam fuer Recherche- und Nachrichten-Agent).

  python3 leads.py add neu.json      Leads aus JSON-Liste hinzufuegen (Duplikate werden uebersprungen)
  python3 leads.py export DATEI.csv  Leads eines Laufs (--lauf JJJJ-MM-TT) oder alle als CSV fuer Google Sheets
  python3 leads.py staedte           naechste noch kaum abgedeckte Staedte vorschlagen
  python3 leads.py status            Uebersicht nach Kategorie und Status
  python3 leads.py setze NAME status=angeschrieben notiz="..."   Status pflegen
"""
import csv
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
DB = ROOT / "leads.csv"
CFG = json.loads((ROOT / "config.json").read_text())
FIELDS = ["id", "lauf", "kategorie", "name", "stadt", "quelle", "kontakt", "aufhaenger", "status",
          "nachricht_dm", "betreff", "nachricht_formular", "notiz"]
STATI = ["neu", "angeschrieben", "geantwortet", "gespraech", "partner", "kein_interesse"]


def norm(s):
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", s)


def load():
    if not DB.exists():
        return []
    with DB.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save(rows):
    with DB.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)


def add(path):
    rows = load()
    seen = {norm(r["name"]) for r in rows}
    new = json.loads(Path(path).read_text())
    nid = max([int(r["id"]) for r in rows], default=0)
    added = skipped = 0
    for l in new:
        if norm(l["name"]) in seen:
            skipped += 1
            continue
        nid += 1
        row = {k: "" for k in FIELDS}
        row.update(l)
        row.update(id=str(nid), lauf=l.get("lauf", date.today().isoformat()), status=l.get("status", "neu"))
        rows.append(row)
        seen.add(norm(l["name"]))
        added += 1
    save(rows)
    print(f"{added} neu, {skipped} Duplikate uebersprungen, gesamt {len(rows)}")


def export(path, lauf=None):
    rows = [r for r in load() if not lauf or r["lauf"] == lauf]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} Leads -> {path}")


def staedte():
    c = Counter(norm(r["stadt"]) for r in load())
    ranked = sorted(CFG["staedte"], key=lambda s: c.get(norm(s), 0))
    print(", ".join(ranked[:6]))


def status():
    rows = load()
    print("Kategorien:", dict(Counter(r["kategorie"] for r in rows)))
    print("Status:", dict(Counter(r["status"] for r in rows)))


def setze(name, *pairs):
    rows = load()
    hit = [r for r in rows if norm(name) in norm(r["name"])]
    if len(hit) != 1:
        sys.exit(f"{len(hit)} Treffer fuer '{name}' - genauer angeben")
    for p in pairs:
        k, v = p.split("=", 1)
        if k == "status" and v not in STATI:
            sys.exit(f"Status muss einer von {STATI} sein")
        hit[0][k] = v
    save(rows)
    print("ok:", hit[0]["name"], {p.split('=')[0]: p.split('=', 1)[1] for p in pairs})


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "add":
        add(a[1])
    elif a[0] == "export":
        export(a[1], a[3] if len(a) > 3 and a[2] == "--lauf" else None)
    elif a[0] == "staedte":
        staedte()
    elif a[0] == "status":
        status()
    elif a[0] == "setze":
        setze(a[1], *a[2:])
