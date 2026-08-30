# RevvBase – Handoff

Detta dokument är en komplett översikt av RevvBase: vad det är, hur koden är
strukturerad, hur man kör och utvecklar lokalt, vilka funktioner som finns, och
vad som återstår att göra. Tänkt som startpunkt för den som tar över eller
återupptar arbetet.

Senast uppdaterad: 2026-07-14.

---

## 1. Vad är RevvBase?

RevvBase är ett webbaserat system för fordonsverkstäder som håller koll på
serviceintervall per fordon. Varje verkstad ("verkstad") lägger in sina bilar,
registrerar utförda serviceåtgärder och milställningar, och systemet räknar ner
till nästa service per servicetyp och varnar när det närmar sig.

Systemet är multi-tenant: flera verkstäder delar samma installation men ser bara
sina egna data. Det finns en global superadmin för att administrera verkstäder
och abonnemangspaket.

---

## 2. Teknisk stack

- **Backend:** Python + Flask (en enda fil, `app.py`, ~2200 rader).
- **Databas:** SQLite (`verkstad.db`), rå `sqlite3` utan ORM. `conn.row_factory = sqlite3.Row`.
- **Vyer:** Jinja2-mallar i `templates/`, statiska filer i `static/`.
- **Auth:** Flask-Login för användare; separat superadmin-session.
- **Formulärskydd:** Flask-WTF (CSRF på alla POST).
- **Produktion:** Gunicorn via `wsgi.py`.
- **E-post:** Resend HTTP-API (via `urllib.request`, inget mail-bibliotek).

---

## 3. Repostruktur

```
revvbase/
├── app.py                  # Hela applikationen: routes, DB, logik
├── wsgi.py                 # Produktionsentry (Gunicorn): init_db, seed-admin, backup-tråd
├── superadmin.py           # (äldre hjälpfil för superadmin)
├── altitud_admin_api.py    # Blueprint: admin-API för externt CRM (Altitud Media)
├── requirements.txt        # Python-beroenden (UTF-8)
├── seed_dummy.py           # Dummy-data för lokal test (bilar + fordonsmodeller)
├── run-local.sh            # Startar appen lokalt (venv + .env + kör)
├── .env.example            # Mall för lokala miljövariabler
├── landing.html            # Publik landningssida (serveras som råfil, ej Jinja)
├── CLAUDE.md               # Arkitekturöversikt för AI-assistenter
├── DEV.md                  # Lokal dev-guide
├── CHANGELOG.md            # Ändringslogg
├── HANDOFF.md              # Detta dokument
├── templates/              # Jinja2-mallar (se nedan)
└── static/
    ├── css/style.css
    └── js/app.js
```

Ignoreras av git (`.gitignore`): `.env`, `venv/`, `verkstad.db`, `.backups/`,
`__pycache__/`, `.secret_key`, `.claude/`.

**Mallar:** `base.html` (delad layout), `index.html` (bil-lista/startsida),
`bil.html` (bilprofil), `ny_bil.html`, `redigera_bil.html`, `ny_handelse.html`,
`redigera_handelse.html`, `kommande.html` (kommande service),
`arbetsorder.html`, `fordonsbibliotek.html` + `ny_/redigera_fordonsmodell.html`,
`importera_miltal.html`, `admin.html`, `mitt_konto.html`, `login.html`,
`pausad.html`, `print_bil.html`, samt `superadmin*.html` (egen mörk layout).

---

## 4. Arkitektur och nyckelbegrepp

**Multi-tenancy.** Varje verkstad har ett `slug` och allt (bilar, användare)
scopas på `verkstad_id`. Roten `GET /` är publik landningssida; `GET /<slug>` är
verkstadens ingång som sätter `session["verkstad_id"]` och går till dashboard.
`check_bil_access()` och `check_aktiv()` är de centrala åtkomstkontrollerna högst
upp i de flesta bil-routes. En admin-användare med `verkstad_id = NULL` ser alla
verkstäders bilar (används av standard-admin och superadmin-liknande konton).

**Roller.** `admin` och `anställd`. Admin hanterar användare inom sin egen
`verkstad_id`. Superadmin (`session["superadmin"]`) är en separat global session
med egen 30-minuters timeout, helt skild från Flask-Login.

**Schemaevolution.** `init_db()` använder `CREATE TABLE IF NOT EXISTS` +
`ALTER TABLE` i `try/except` för idempotenta migreringar. Inget migreringsramverk.

**Serviceintervall-logik (prioritetsordning):**
1. Per-fordon-överskrivningar i tabellen `serviceintervall`.
2. Verkstadsspecifika fordonsmodell-mallar (`fordonsmodeller` / `fordonsmodell_intervall`).
3. Hårdkodad `STANDARD_INTERVALL`-dict som sista fallback.

`bygg_panel()` räknar ut nedräkning per servicetyp genom att jämföra senaste
milställning mot senaste gången den servicetypen utfördes (i `handelser`).

**Servicetyper (redigerbara per verkstad).** Tabellen `servicetyper` håller en
lista per verkstad. Varje typ kan ha flaggan `har_intervall` (visas som
km-checkbox vid ny bil/modell och ger nedräkning) och ett förvalt `standard_km`.
Hjälpfunktioner: `get_service_typer()` (alla, för loggning),
`get_nedraknare_typer()` (de med km-intervall), `get_nedraknare_standardkm()`
(förvalen). Hårdkodade `SERVICE_TYPER` / `NEDRAKNARE_TYPER` används bara som
fallback tills verkstaden sparat egna (seedas vid första besök på admin-sidan).

**Paketbegränsningar.** `get_paket_limits()` läser tabellen `paketinstallningar`
(redigeras av superadmin på `/superadmin/paket`), med hårdkodade standardvärden
som fallback. Paket: `bas`, `standard`, `pro`.

**Backuper.** `daglig_backup()` körs i en daemon-tråd och skriver per-verkstad
CSV till `BACKUP_DIR/<slug>/<datum>.csv` en gång per dag. Superadmin kan trigga
manuell backup via `POST /superadmin/backup`.

**Säkerhet.** CSRF på alla POST. Brute-force-skydd via in-memory-dictar
(`_login_attempts` / `_sa_login_attempts`, 5 försök, 15 min lockout).
Säkerhetsheaders i `@app.after_request`. Lösenord hashas med `pbkdf2:sha256`
(explicit, för Azure-kompatibilitet).

---

## 5. Databasschema (tabeller)

- **bilar** – `id, regnr, fordonsnummer, marke, modell, arsmodell, notering, verkstad_id` (UNIQUE regnr+verkstad_id).
- **handelser** – `id, bil_id, datum, km, typ ('service'|'fel'|'miltal'), service_typer (JSON-lista), beskrivning, skapad_av`.
- **serviceintervall** – per-fordon-överskrivning: `bil_id, service_typ, intervall_km, aktiv`.
- **fordonsmodeller** – mallar: `marke, modell, arsmodell, verkstad_id`.
- **fordonsmodell_intervall** – `fordonsmodell_id, service_typ, intervall_km, aktiv`.
- **kommentarer** – noteringar på bilprofilen: `bil_id, text, skapad_av, datum`.
- **anvandare** – `username, namn, password_hash, roll, verkstad_id, senaste_inloggning, session_token`.
- **verkstader** – `namn, slug, admin_email, paket, status ('aktiv'|'pausad'), skapad`.
- **paketinstallningar** – gränser per paket (användare/bilar, obegränsat-flaggor, pris).
- **servicetyper** – redigerbara servicetyper per verkstad: `verkstad_id, kategori ('service'), namn, ordning, har_intervall, standard_km`.

---

## 6. Routes (översikt)

**Publikt / auth:** `/` (landning), `/<slug>` (verkstadsingång), `/login`, `/logout`.

**Dashboard & bilar:** `/dashboard`, `/bil/ny`, `/bil/<id>`, `/bil/<id>/redigera`,
`/bil/<id>/ny-handelse`, `/bil/<id>/redigera-handelse/<h_id>`,
`/bil/<id>/ny-kommentar`, `/bil/<id>/ta-bort-kommentar/<k_id>`,
`/bil/<id>/ta-bort-handelse/<h_id>`, `/bil/<id>/ta-bort`, `/bil/<id>/print`.

**Service & planering:** `/kommande` (bilar som närmar sig service),
`/arbetsorder` (POST, skapar arbetsorder för valda bilar).

**Fordonsbibliotek:** `/fordonsbibliotek`, `/fordonsbibliotek/ny`,
`/fordonsbibliotek/<id>/redigera`, `/fordonsbibliotek/<id>/ta-bort`.

**Import/export:** `/importera-miltal` (CSV med kolumnmappning), `/exportera`.

**Admin (per verkstad):** `/admin`, `/admin/ny` (användare),
`/admin/byt-losenord/<id>`, `/admin/ta-bort/<id>`,
`/admin/servicetyp/ny`, `/admin/servicetyp/standard-km/<id>`,
`/admin/servicetyp/toggla-intervall/<id>`, `/admin/servicetyp/ta-bort/<id>`.
`/mitt-konto` (byt eget lösenord).

**Superadmin (global):** `/superadmin/login`, `/superadmin`, `/superadmin/ny`,
`/superadmin/pausa/<id>`, `/superadmin/ta-bort/<id>`, `/superadmin/redigera/<id>`,
`/superadmin/paket`, `/superadmin/byt-losenord/<id>`, `/superadmin/backup`,
`/superadmin/logout`.

**Admin-API (blueprint `altitud_admin_api.py`):** `/api/admin/summary`,
`/api/admin/tenants` (POST), `/api/admin/tenants/<id>/toggle` (POST),
`/api/admin/tenants/<id>` (DELETE). Skyddas av `ADMIN_API_KEY`. Låter ett externt
CRM (Altitud Media) hantera verkstäder live.

---

## 7. Funktioner

- **Bil-lista (startsida)** med sök på reg.nr/fordonsnr/märke, och kort som visar
  fordonsnummer, reg.nr, märke/modell/år, `notering` samt senaste kommentaren
  från bilprofilen.
- **Bilprofil** med servicehistorik, nedräkningspanel per servicetyp, egna
  noteringar (kommentarer) och utskrift.
- **Registrera händelser:** milställning, utförd service (välj servicetyper) och fel.
- **Kommande service** – lista över bilar som närmar sig eller passerat intervall,
  med möjlighet att skapa arbetsorder.
- **Fordonsbibliotek** – mallar per märke/modell med förinställda serviceintervall.
- **Redigerbara servicetyper per verkstad** (Admin → Servicetyper): en lista där
  varje typ kan markeras med km-intervall och få ett förvalt km-värde. Km-typer
  sorteras automatiskt överst; toggle och förval sparas i bakgrunden (ingen
  omladdning/scroll).
- **CSV-import av milställningar** i två steg med kolumnmappning: robust inläsning
  (UTF-8/Windows-1252/Latin-1), automatisk avgränsar-detektering (`;`, `,`, tab,
  `|`), stöd för filer utan rubrikrad, och korrekt km-tolkning (decimalkomma
  kapas, mellanslag som tusental). Förhandsvisning och automatiska gissningar.
- **Export** av all data till CSV.
- **Utskrift** av bilens servicehistorik (endast service; "fel" och milställningar
  exkluderas; åtgärder listas).
- **Användaradministration** per verkstad, med paketgränser.
- **Superadmin-panel** för verkstäder, paket och backup.

---

## 8. Lokal utveckling

Se `DEV.md` för detaljer. Kort:

```bash
cd ~/Claude/Projects/revvbase
./run-local.sh          # skapar venv, installerar beroenden, laddar .env, kör
```

Öppna http://localhost:5001. Standardinlogg (skapas vid första start):
**admin / verkstad123**. `run-local.sh` skapar `.env` från `.env.example` första
gången. Med `FLASK_DEBUG=1` laddar servern om automatiskt.

**Dummy-data:** `python seed_dummy.py` (i aktiverad venv) lägger in 10 bilar med
milställning/servicehistorik och 4 fordonsmodeller. Idempotent.

**Miljövariabler** (`.env.example`): `PORT`, `FLASK_DEBUG`, `DB_PATH`,
`BACKUP_DIR` (måste sättas lokalt – default `/home/data/...` finns inte på macOS),
`SUPERADMIN_PASSWORD` (krävs för att appen ska starta), `RESEND_API_KEY` (valfritt,
för mail), samt `ADMIN_API_KEY` (för admin-API:t).

---

## 9. Produktion

Körs via Gunicorn med `wsgi.py` som entry (kör `init_db()`, seedar admin, startar
backup-tråd). Driftsatt miljö (Azure App Service) har egen databas – lokal
testdata påverkar den inte. Produktionsinställningar sätts via App Service →
Configuration → Application settings (bl.a. `SUPERADMIN_PASSWORD`, `SECRET_KEY`,
`RESEND_API_KEY`, `BACKUP_DIR`).

---

## 10. Arbetssätt (git)

- Arbeta i `~/Claude/Projects/revvbase` (arbetskopian).
- Testa lokalt med `./run-local.sh` innan commit.
- Committa och pusha när en funktion är klar – inte per liten ändring.
- Push körs från egen terminal (`git push origin main`); molnmiljön saknar
  GitHub-inloggning.
- Remote: `github.com/Svayak/RevvBase_V2`, branch `main`.
- Håll `CHANGELOG.md` uppdaterad per pushad ändring.

---

## 11. Kända begränsningar / fallgropar

- **Servicetyp-ändringar gäller bara framåt.** Att lägga till/ta bort en
  servicetyp eller ändra förval påverkar nya bilar/modeller – inte redan
  registrerade bilars intervall.
- **Login-etikett.** Fältet heter fortfarande "E-post" men inloggning sker med
  användarnamn (fältet är numera `type="text"`).
- **Inget migreringsramverk.** Schemaändringar görs med `ALTER` i `try/except`.
  Fungerar men blir svårare att överblicka över tid.
- **SQLite.** Enkel drift men begränsad samtidighet; vid tillväxt kan Postgres
  behövas.
- **Inga automatiska tester i repot.** Verifiering har skett manuellt/i sandbox.
- **CSV-import validerar inte datumformat** (sparas som text rakt av).
- **Testdata i produktion.** Om dummy-bilar (t.ex. "Okänt märke"-bilarna från
  Bok1.csv-testet eller `seed_dummy.py`) råkat hamna i en riktig databas bör de
  rensas innan skarp drift.
- **Backup saknar återställnings-UI** – CSV skrivs men återläsning görs manuellt.

---

## 12. TODO / nästa steg

Prioriterat:

- [ ] Möjlighet att applicera ändrade servicetyper/förval även på **befintliga**
  bilar (inte bara nya).
- [ ] Byt login-etiketten "E-post" → "Användarnamn" (eller stöd båda tydligt).
- [ ] Rensa eventuell testdata (dummy-bilar) ur skarp databas.

Bra att ha:

- [ ] Gör "lägg till / ta bort servicetyp" helt i bakgrunden (som toggeln), så
  hela admin-sidan slipper laddas om.
- [ ] Datumvalidering vid CSV-import (och stöd för fler datumformat).
- [ ] Automatiska tester (pytest) för de centrala flödena: åtkomstkontroll,
  serviceintervall-beräkning, CSV-import, servicetyper.
- [ ] Återställningsfunktion från backup i superadmin-panelen.
- [ ] Överväg riktigt migreringsverktyg om schemat fortsätter växa.

Längre sikt:

- [ ] Utvärdera Postgres om antalet verkstäder/bilar växer.
- [ ] Notiser (e-post) när bilar närmar sig service.

---

## 13. Referenser

- `CLAUDE.md` – kortare arkitekturöversikt (för AI-assistenter).
- `DEV.md` – lokal dev-guide.
- `CHANGELOG.md` – detaljerad ändringslogg per datum.
