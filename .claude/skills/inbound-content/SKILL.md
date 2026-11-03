---
name: inbound-content
description: Inbound-Agent fuer customweddingsites.de - sorgt dafuer, dass Brautpaare das Album selbst finden. Recherchiert Suchthemen, schreibt SEO-Ratgeberartikel (Google) und erzeugt passende Pinterest-Pins (Bilder 1000x1500 + Titel/Beschreibung/Keywords als CSV). Nutzen bei "neuer Artikel", "Pins", "Pinterest", "SEO", "Content", "/inbound-content".
---

# Inbound-Content-Agent

Ziel: Paare suchen bei Google und Pinterest nach Loesungen ("Hochzeitsfotos von Gaesten sammeln", "Fotospiel Hochzeit" ...).
Wir beantworten diese Fragen besser als alle anderen und verlinken auf customweddingsites.de. Kein Anschreiben, keine Werbe-Mails.

Alles liegt in `inbound/`:

| Datei | Zweck |
|---|---|
| `config.json` | Marke, Link, Produktfakten (nur diese behaupten), Tonalitaet, Pinterest-Boards |
| `themen.json` | Themenliste mit Keyword, Art und Status (offen / geschrieben / veroeffentlicht) |
| `artikel/<slug>.md` | Fertige Artikel mit Meta-Titel und Meta-Beschreibung |
| `pins/<slug>/pins.json` | Pin-Spezifikation; `python3 pins.py pins/<slug>/pins.json` rendert `pin_XX.png` + `pins.csv` |

## Ablauf pro Lauf (Standard: 1 Artikel + 5 Pins)

1. Naechstes Thema mit `"status": "offen"` aus `themen.json` nehmen (oder ein neues, wenn der Nutzer eins nennt).
   Neue Themen finden: WebSearch nach Fragen von Paaren (Foren, "Hochzeit ... Tipps", "... Ideen"), Themen mit klarem
   Bezug zu Gaestefotos, Gaeste-Unterhaltung, Deko mit QR-Code, Erinnerungen bevorzugen. Neue Themen in `themen.json` ergaenzen.
2. Mit WebSearch pruefen, was zu dem Keyword schon rankt. Unser Artikel muss hilfreicher sein: konkreter, ehrlicher, mit Liste/Tabelle und FAQ.
3. Artikel schreiben (`artikel/<slug>.md`):
   - Frontmatter: title (max. ca. 60 Zeichen, Keyword vorne), meta_description (max. 155 Zeichen), keyword, slug.
   - 800-1500 Woerter, Du/Ihr, H2-Gliederung, kurze Absaetze, eine Liste oder Vergleich, 3-5 FAQ am Ende.
   - Erst wirklich helfen, das Produkt erst als eine Option von mehreren (fair!) und am Ende ein CTA zur kostenlosen Vorschau.
   - Nur Fakten aus `config.json`. Keine erfundenen Zahlen, Studien oder Preise anderer Anbieter.
4. 5 Pins in `pins/<slug>/pins.json` anlegen, Layouts mischen (`titel` mit Foto, `liste`, `frage`, `schritte`),
   verschiedene Themes/Fonts aus `adagent/patterns.json`. Akzent mit `*Wort*` oder `*mehrere Woerter*`.
   Pin-Titel max. 100 Zeichen, Beschreibung 2-3 Saetze mit Keywords + 3-5 Hashtags, Alt-Text, Board aus config.
5. `cd inbound && python3 pins.py pins/<slug>/pins.json` und die PNGs ansehen (Read). Text darf nicht abgeschnitten sein.
6. Status in `themen.json` auf `geschrieben` setzen, committen, pushen, Artikel + Pins + pins.csv per SendUserFile schicken.

## Was der Nutzer danach tut

- Artikel auf der Website als Blogbeitrag veroeffentlichen (Text kopieren, Meta-Titel/-Beschreibung eintragen), dann Status `veroeffentlicht`.
- Pins bei Pinterest (Business-Konto) hochladen, Link auf den Artikel setzen, Titel/Beschreibung aus `pins.csv`.
  Pinterest erlaubt Bulk-Upload per CSV, braucht dafuer aber oeffentliche Bild-URLs ("Media URL").
- Ergebnisse (Pinterest-Impressionen/Klicks, Google Search Console) mitteilen -> Themen, die laufen, vertiefen.
