# Assets – Werbevideo Hochzeitsalbum

| Slot | Datei | Quelle | Lizenz | Urheber |
|---|---|---|---|---|
| A – Hook-Foto | `assets/hook_placeholder.jpg` | **Platzhalter**, per Skript generiert (`placeholder_hook` in `build.py`) | eigenes Werk | – |
| B – Problem-Visual | – | nicht verwendet (optional) | – | – |
| C – Produktkarte | `assets/app_card_placeholder.png` | **Platzhalter**, nachgebauter Album-Screen | eigenes Werk | – |
| Schrift | `fonts/InterTight-*.ttf` | Google Fonts (Inter Tight) | SIL Open Font License 1.1 | Vernon Adams / Inter Tight Project |
| Stimme | (generiert) | espeak-ng + MBROLA de7 (lokal) | Entwurf, kein Endprodukt | – |

## Austauschen
- Echtes Hook-Foto als `assets/hook.jpg` ablegen (≥ 3840 px, freie Lizenz) – wird automatisch für 16:9 und 9:16 zugeschnitten.
- Echten App-Screenshot als `assets/app_screenshot.png` ablegen – wird automatisch in den Handyrahmen gesetzt.
- Marke/URL: `BRAND` und `BRAND_END` oben in `build.py`.
- Danach `python3 build.py` erneut ausführen.
