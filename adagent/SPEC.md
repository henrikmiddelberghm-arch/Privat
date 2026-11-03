# Spec-Format (specs/ad_XXX.json)

```json
{
  "id": "ad_005",
  "formats": ["9x16", "16x9"],
  "theme": "night_gold",            // id aus patterns.json -> themes
  "font": "anton",                  // id aus patterns.json -> fonts
  "pacing": "schnell",              // ruhig | normal | schnell
  "patterns": { ... },              // vom Generator, nur Doku
  "assets": {"hook": "assets/hook.jpg", "screenshot": "assets/app.png", "placeholder_seed": 12},
  "scenes": [ ... ]
}
```

Eine **Zeile** ist ein String oder ein Objekt:
`{"text": "Ohne App, ohne Konto.", "role": "big", "accent": ["Konto."], "say": "optionale Aussprache", "silent": false}`
Jedes angezeigte Wort wird gesprochen und erscheint genau auf dem gesprochenen Wort (Karaoke).
`accent` listet die Woerter in Akzentfarbe (exakt wie im Text, mit oder ohne Satzzeichen).

**Rollen:** `small`, `big`, `huge`, `grey`, `italic`, `body`, `number` (zaehlt hoch), `list`, `cta`, `price`, `brand`, `before`, `after`, `punch`.

## Szenentypen

| type | Felder | Wirkung |
|---|---|---|
| `photo_hook` | `lines` | Vollbild-Foto mit Push-in 100->108 % und Vignette, weisser Text |
| `statement` | `lines`, optional `bg`: `bg` / `accent` / `fg` | Gestapelte Zeilen mit Rollen; mit `role: number` = Zahlen-Hook |
| `blur_list` | `items` | Blur-Stapel, aktive Zeile scharf mit Pfeil, Spring-Gleiten pro Beat, Tick |
| `checklist` | `items` | Punkte erscheinen untereinander mit animiertem Haken, Tick |
| `punch` | `lines` | Jedes Wort einzeln bildschirmfuellend, Hintergrund wechselt pro Wort |
| `split` | `before`, `after` | Vorher (durchgestrichen) / Nachher (Akzentflaeche faehrt ein) |
| `payoff_card` | `lines` (1 oder 2) | Payoff-Text + Produktkarte mit 3D-Kippung, Riser + Hit auf Akzentwort |
| `cta_end` | `cta`, `price`, `brand`, `brand_end` | CTA-Karaoke, dann Endkarte (Preis gesprochen, Marke still) |

Jede Szene hat `transition`: `cut`, `blur_wipe`, `wipe_up`, `slide`, `zoom`, `flash` (Uebergang *in* diese Szene).

## Ton
Sprecher (Entwurf: espeak-ng + MBROLA de7), Tick bei Listen/Punch-Beats, Whoosh bei Uebergaengen,
Riser in den Payoff, Hit auf das Payoff-Akzentwort. Master -14 LUFS / -1 dBTP (zwei Durchgaenge loudnorm).
Aussprache-Korrekturen: `PRON` in `engine.py` erweitern oder pro Zeile `say` setzen.
