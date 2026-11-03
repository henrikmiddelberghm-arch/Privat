---
name: partner-akquise
description: Partner-Akquise fuer customweddingsites.de. Agent 1 recherchiert neue Hochzeits-Dienstleister in Deutschland (Planer, Locations, Fotografen, DJs, Trauredner), Agent 2 schreibt fuer jeden eine persoenliche Kooperationsanfrage (Instagram-DM + Kontaktformular). Nie selbst versenden. Nutzen bei "neue Partner finden", "Akquise", "Leads", "Kooperationsanfragen", "/partner-akquise".
---

# Partner-Akquise (2 Agenten)

Alles liegt in `akquise/` (Befehle dort ausfuehren).

| Datei | Zweck |
|---|---|
| `config.json` | Marke, Produktfakten, Angebot an Partner, Kategorien mit Suchmustern, Staedteliste, Anzahl pro Lauf |
| `leads.csv` | Gemeinsame Lead-Datenbank (nie von Hand leeren). Duplikate werden automatisch erkannt. |
| `leads.py` | `add`, `export`, `staedte`, `status`, `setze` |
| `laeufe/JJJJ-MM-TT.json` | Rohdaten eines Laufs |
| `partner_JJJJ-MM-TT.csv` | Ergebnis eines Laufs fuer den Nutzer (Excel/Numbers/Google Sheets) |

## Harte Regeln

- **Nie selbst versenden** - weder E-Mail noch DM noch Formular. Nur Entwuerfe; der Nutzer prueft und sendet.
- Keine E-Mail-Massenmails. Unaufgeforderte Werbe-E-Mails sind in Deutschland (§ 7 UWG) unzulaessig. Kanal ist
  Instagram-DM (einzeln, von Hand) oder das Kontaktformular des Partners.
- Nur **oeffentlich gelistete Firmen** und deren geschaeftliche Kontaktwege. Keine Privatpersonen, keine privaten Daten.
- Aufhaenger nur aus dem, was die Quelle wirklich sagt. Nichts erfinden (keine erfundenen Bewertungen, Zahlen, Preise).
- Angebot an Partner laut `config.json`: **keine Provision, kein Rabatt**, reines Kennenlernen fuer spaetere Zusammenarbeit.
  Nutzen fuer den Partner ist ein Extra fuer seine Paare. Nichts versprechen, was nicht in `config.json` steht.

## Agent 1 - Partner-Recherche

1. `python3 leads.py staedte` -> die am wenigsten abgedeckten Staedte nehmen (2-4 pro Lauf).
2. Pro Kategorie aus `config.json` -> Suchmuster mit Stadt einsetzen und mit **WebSearch** suchen (mehrere Suchen parallel).
   Verzeichnisse wie Bridebook, werkenntdenbesten, trustlocal, golocal, Branchenbuecher sind ok als Quelle.
3. Pro Treffer erfassen: `kategorie`, `name` (Firma/Person), `stadt`, `quelle` (exakte URL aus dem Suchergebnis),
   `kontakt` (nur was oeffentlich im Ergebnis steht, sonst "Website/Instagram pruefen"), `aufhaenger`
   (ein konkretes, belegtes Detail: Lage, Stil, Erfahrung, Bewertungen ...).
4. Ziel: `pro_lauf` Leads, Kategorien gemischt. Lieber weniger, dafuer echte Firmen mit eindeutigem Namen.
   Agenturen, die keine Hochzeiten machen, und reine Vermittlungsportale weglassen.

Hinweis: Die Cloud-Umgebung kann viele Websites nicht direkt abrufen. Deshalb nur Daten aus den Suchergebnissen nutzen
und in `notiz` vermerken: "vor dem Senden auf der Website pruefen".

## Agent 2 - Nachrichten

Fuer jeden neuen Lead zwei Texte schreiben:

- `nachricht_dm` (Instagram, Du/Ihr): Anrede mit Vorname bei Einzelpersonen ("Hallo Leonardo"), sonst "Hallo liebes
  Team von ..." und dann **ihr**-Form. Aufbau: 1) wer ich bin (Henrik von customweddingsites.de) 2) der persoenliche
  Aufhaenger 3) Produkt in 1-2 Saetzen (QR-Code, Name, Fotos hochladen, ohne App/Konto, alles an einem Ort)
  4) kategoriespezifischer Nutzen fuer **seine Paare** 5) "Ich verkaufe dir hier nichts" + Wunsch nach kurzem
  Austausch + Angebot kostenlose Vorschau 6) "Liebe Gruesse, Henrik". Max. ca. 700 Zeichen.
- `betreff` + `nachricht_formular` (Kontaktformular, Sie-Form, gleicher Aufbau, Signatur mit customweddingsites.de).

Kategorie-Nutzen (Vorlage, frei variieren - nicht jede Nachricht gleich):
Planer: Extra fuer eure Paare ohne Arbeit · Location: QR-Aufsteller auf den Tischen reicht ·
Fotograf: keine Konkurrenz, Ergaenzung um die Gaeste-Schnappschuesse · DJ: Tanzflaeche wird viel fotografiert ·
Trauredner: bei freien Trauungen fotografieren viele Gaeste mit.

## Ablauf eines Laufs

```bash
cd akquise
python3 leads.py staedte
# ... recherchieren + Texte schreiben -> laeufe/$(date +%F).json  (Liste von Objekten mit den Feldern oben)
python3 leads.py add laeufe/$(date +%F).json
python3 leads.py export partner_$(date +%F).csv --lauf $(date +%F)
```
CSV als UTF-8 mit BOM speichern (fuer Excel), per SendUserFile schicken, committen und pushen.
Dem Nutzer kurz melden: Anzahl, Staedte, Kategorien, 1 Beispielnachricht, Hinweis "vor dem Senden kurz Website pruefen".

## Status pflegen

Wenn der Nutzer meldet, wen er angeschrieben hat oder wer geantwortet hat:
`python3 leads.py setze "Leonardo" status=angeschrieben notiz="DM am 04.11."`
Stati: neu, angeschrieben, geantwortet, gespraech, partner, kein_interesse.
Bei "angeschrieben" ohne Antwort nach 7-10 Tagen: eine kurze, freundliche Nachfass-Nachricht entwerfen (nur einmal).
