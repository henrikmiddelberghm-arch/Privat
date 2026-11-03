---
name: ad-video-agent
description: Erstellt immer neue, unterschiedliche Kinetic-Typography-Video-Ads (9:16 + 16:9, 60 fps, 15-20 s, Deutsch) fuer das Produkt in adagent/product.json. Recherchiert Ad-Muster, analysiert hochgeladene Beispiel-Ads, erzeugt ein neues Briefing ohne Wiederholung, schreibt die Texte, rendert und prueft die Videos. Nutzen bei "mach neue Ads", "neues Werbevideo", "analysiere diese Ad", "/ad-video-agent".
---

# Ad-Video-Agent

Alles liegt in `adagent/`. Arbeitsverzeichnis fuer alle Befehle: `adagent/`.

| Datei | Zweck |
|---|---|
| `patterns.json` | Musterbibliothek (Hooks, Turns, Bodies, Payoffs, CTAs, Angles, Farbwelten, Schriften, Tempo) mit Begruendung und Quelle |
| `product.json` | Produktfakten, Marke, Preis, Asset-Pfade. **Nur diese Fakten duerfen behauptet werden.** |
| `brief.py` | Waehlt eine noch nie genutzte Musterkombination, schreibt `briefs/ad_XXX.md` + `specs/ad_XXX.json` (Texte = TODO) |
| `engine.py` | Rendert eine Spec: `--check` (Timeline), `--preview` (Kontaktbogen), ohne Flag = Videos |
| `analyze_ad.py` | Zerlegt eine Beispiel-Ad (Schnitte, Tempo, Hook-Bilder, Farben, Lautheit) |
| `SPEC.md` | Spec-Format und Szenentypen |
| `history.json` | Bereits genutzte Kombinationen (nicht von Hand loeschen) |
| `results.json` | Optionale Performance-Ergebnisse, die der Nutzer liefert |

## 0. Umgebung pruefen

```bash
which espeak-ng ffmpeg || (apt-get update -qq && apt-get install -y -qq espeak-ng mbrola mbrola-de7)
ls /usr/share/mbrola/de7 && python3 -c "import PIL, numpy"
```

## 1. Muster lernen (wenn der Nutzer Ads liefert oder Recherche will)

**Vom Nutzer gelieferte Ads** (Videodateien im Repo oder hochgeladen):
1. `python3 analyze_ad.py <video> --name <kurzname>` ausfuehren.
2. `analysis/<name>/hook.png` und `cuts.png` mit dem Read-Tool ansehen, `report.json` lesen.
3. Markantes benennen: Was passiert in den ersten 0,5 / 1 / 3 s? Schnitte pro Sekunde, Textgroesse und -menge pro Einblendung, Farbkontrast, Szenenaufbau (Problem -> Loesung -> Beweis -> CTA?), Art des CTA.
4. Daraus **Muster** ableiten und in `patterns.json` ergaenzen (neue `id`, `desc`, `why` mit Verweis auf die Analyse). Wenn ein Muster einen neuen Szenentyp braucht, den `engine.py` nicht kann, das dem Nutzer sagen und vorschlagen, ihn einzubauen.
5. Performance-Zahlen kommen nur vom Nutzer (eigener Werbeaccount, TikTok Creative Center, Meta Ad Library). Ohne Zahlen von "Beobachtung", nicht von "Gewinner" sprechen.

**Web-Recherche:** WebSearch nach aktuellen Hook- und Kreativ-Mustern (Plattform-Guides von TikTok/Meta zuerst, Vendor-Blogs nur als weiches Signal). Neue Erkenntnisse mit Quelle in `patterns.json` -> `sources`/`principles` bzw. als Muster eintragen.

**Grenze:** Muster, Aufbau, Tempo und Stilmittel uebernehmen - **nie** fremde Texte, Slogans, Logos, Markenfarben-Kombinationen oder Bildmaterial 1:1 kopieren.

## 2. Neues Briefing

```bash
python3 brief.py
```
`briefs/ad_XXX.md` lesen. Die Kombination ist garantiert neu und unterscheidet sich in mindestens 4 Dimensionen von jeder der letzten 5 Ads.

## 3. Texte schreiben (in `specs/ad_XXX.json` alle TODO ersetzen)

- Deutsch, Du/Ihr-Ansprache an das Brautpaar, **max. 6 Woerter pro Zeile**, Listenpunkte max. 4 Woerter.
- Nur Fakten aus `product.json`. **Keine erfundenen Statistiken**, keine falsche Dringlichkeit, keine Testimonials.
- Hook passend zum gewaehlten Hook-Muster und Angle; das erste Wort muss in < 0,5 s kommen.
- Pro Szene hoechstens 1-2 Akzentwoerter (`accent`), meist das Schluesselwort des Problems bzw. Nutzens.
- Neue Formulierungen: vorher die Hook- und CTA-Zeilen aller bestehenden `specs/*.json` lesen und nichts wiederholen.
- Woerter, die die Entwurfsstimme falsch ausspricht: `say` setzen oder `PRON` in `engine.py` ergaenzen.
- Die Marke bleibt `MARKE` / `.de`, bis der Nutzer sie in `product.json` eintraegt.

## 4. Pruefen und Vorschau

```bash
python3 engine.py specs/ad_XXX.json --check     # Laenge 15-20 s, keine WARNUNG
python3 engine.py specs/ad_XXX.json --preview   # out/ad_XXX_preview_9x16.png + _16x9.png
```
Beide Vorschaubilder mit Read ansehen: Text im sicheren Bereich, nichts ueberlappt, lesbar, Akzentfarbe sinnvoll.
Zu lang -> Texte kuerzen oder `pacing` auf `schnell`. Probleme beheben, dann erneut pruefen.

## 5. Rendern und verifizieren

```bash
python3 engine.py specs/ad_XXX.json     # ca. 1,5 min pro Format
ffprobe -v error -show_entries format=duration:stream=width,height,r_frame_rate -of compact out/ad_XXX_9x16.mp4
ffmpeg -hide_banner -i out/ad_XXX_9x16.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -E "I:|Peak:" | tail -2
```
Erwartet: 1080x1920 bzw. 1920x1080, 60 fps, ca. -14 LUFS, Peak < -1 dB. Stichproben-Frames mit
`ffmpeg -ss <t> -i ... -frames:v 1` ziehen und ansehen.

## 6. Abliefern

- Videos mit SendUserFile schicken (`display: render`).
- Commit + Push (Specs, Briefs, history.json, Videos in `out/`).
- Kurz berichten: gewaehlte Muster und warum (aus dem Briefing), die Texte, was Platzhalter ist (Foto, App-Screenshot, Stimme, Marke).

## 7. Aus Ergebnissen lernen

Wenn der Nutzer Zahlen liefert (z. B. Hook-Rate, CTR, Kosten pro Ergebnis pro Ad-ID), in `results.json` eintragen
(`{"ad_002": {"hook_rate": 0.31, "ctr": 0.012, "notiz": "..."}}`). Muster der besten Ads in `patterns.json` mit
`"weight": 2-3` hochgewichten, klar schwache mit `"weight": 0.3` abwerten. Erst ab mehreren Ads pro Muster gewichten;
Einzelergebnisse nur notieren.

## Platzhalter ersetzen

- Echtes Foto: Datei nach `adagent/assets/` und in `product.json` -> `hook_photo` (gilt fuer neue Briefings) bzw. in der Spec `assets.hook`.
- App-Screenshot: `product.json` -> `screenshot`.
- Stimme: Die Engine nutzt eine lokale Entwurfsstimme. Fuer ElevenLabs braucht es Netzwerkzugang zu api.elevenlabs.io und einen API-Key; dann `tts()` in `engine.py` auf die ElevenLabs-API (mit Wort-Zeitstempeln) umstellen.
