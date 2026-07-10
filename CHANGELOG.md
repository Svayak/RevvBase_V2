# Ändringslogg

Alla noterbara ändringar i RevvBase dokumenteras här.

## 2026-07-10

### Nytt
- **Lokal dev-miljö**: `run-local.sh` startar appen lokalt (skapar venv, installerar beroenden, laddar `.env`). Mall i `.env.example` och instruktioner i `DEV.md`.
- **`seed_dummy.py`**: lägger in 10 dummy-bilar med milställning och servicehistorik för test. Idempotent.
- **Senaste notering på bilkortet**: förstasidans bilkort visar nu den senaste noteringen (kommentaren) som skrivits inne på bilprofilen.
- **Redigerbara servicetyper per verkstad** (Admin → Servicetyper): en gemensam lista där varje typ kan markeras med **km-intervall**. Alla typer är valbara vid loggning av service; de med km-intervall visas som km-fält när man lägger till bil/fordonsmodell och ger nedräkning på bilkortet. Tidigare hårdkodade listor (`NEDRAKNARE_TYPER`/`SERVICE_TYPER`) används nu bara som standard tills en verkstad sparat egna. Ny tabell `servicetyper` med idempotent migrering.
- **Förvalt km-intervall per servicetyp**: varje km-intervall-typ kan ha ett förvalt km-värde som förifylls (och används som fallback vid tomt fält) när man lägger till en ny bil.
- **Auto-sortering i admin**: servicetyper med km-intervall sorteras överst, både vid sidladdning och live när man klickar (utan omladdning). Km-intervall-toggeln och förvals-fältet sparas i bakgrunden så sidan inte scrollar.

### Ändrat
- **CSV-import av miltal** (`/importera-miltal`): helt ombyggd i två steg med kolumnmappning. Läser filen robust (UTF-8/Windows-1252/Latin-1) och känner av avgränsare (`;`, `,`, tab, `|`) — löser tidigare "server error" på Excel-exporterade filer. Man taggar själv vilken kolumn som är reg.nr, km och (valfritt) datum, med förhandsvisning och automatiska gissningar. Stödjer filer utan rubrikrad och tolkar km med decimalkomma/tusentalsmellanslag korrekt.
- **Utskrift av historik** (`/bil/<id>/print`): visar endast servicehistorik — "fel" och milställningar exkluderas. Åtgärder listas server-side (i stället för via JavaScript) och beskrivningstexten "Service utförd" tas inte med; bara de faktiska åtgärderna listas.
- **Inloggning**: e-postfältet är nu ett textfält, eftersom inloggning sker med användarnamn (t.ex. `admin`) och inte kräver `@`.
- **`app.py`**: läser `PORT` och `FLASK_DEBUG` från miljövariabler vid direktkörning (påverkar inte produktion via Gunicorn).

### Fixat
- **`requirements.txt`** var kodad i UTF-16 vilket bröt `pip install` — konverterad till UTF-8.
