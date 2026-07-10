# Ändringslogg

Alla noterbara ändringar i RevvBase dokumenteras här.

## 2026-07-10

### Nytt
- **Lokal dev-miljö**: `run-local.sh` startar appen lokalt (skapar venv, installerar beroenden, laddar `.env`). Mall i `.env.example` och instruktioner i `DEV.md`.
- **`seed_dummy.py`**: lägger in 10 dummy-bilar med milställning och servicehistorik för test. Idempotent.
- **Senaste notering på bilkortet**: förstasidans bilkort visar nu den senaste noteringen (kommentaren) som skrivits inne på bilprofilen.

### Ändrat
- **Utskrift av historik** (`/bil/<id>/print`): visar endast servicehistorik — "fel" och milställningar exkluderas. Åtgärder listas server-side (i stället för via JavaScript) och beskrivningstexten "Service utförd" tas inte med; bara de faktiska åtgärderna listas.
- **Inloggning**: e-postfältet är nu ett textfält, eftersom inloggning sker med användarnamn (t.ex. `admin`) och inte kräver `@`.
- **`app.py`**: läser `PORT` och `FLASK_DEBUG` från miljövariabler vid direktkörning (påverkar inte produktion via Gunicorn).

### Fixat
- **`requirements.txt`** var kodad i UTF-16 vilket bröt `pip install` — konverterad till UTF-8.
