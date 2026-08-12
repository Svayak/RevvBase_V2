# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
# Development
python app.py           # runs on port 5001

# Production (via Gunicorn)
gunicorn wsgi:app
```

`wsgi.py` is the production entry point — it calls `init_db()`, seeds the default admin user, and starts the background backup thread before handing off to Gunicorn. The backup thread is guarded by a non-blocking `fcntl` lock on `BACKUP_DIR/.backup.lock`, so only one Gunicorn worker runs it.

Environment variables:
- `SECRET_KEY` — Flask session key (falls back to `.secret_key` file, then auto-generates)
- `DB_PATH` — SQLite database path (default: `verkstad.db` next to `app.py`)
- `BACKUP_DIR` — CSV backup destination (default: `/home/data/säkerhetskopior`)
- `RESEND_API_KEY` — Required for outgoing email via Resend API
- `SUPERADMIN_PASSWORD` — **Required.** The app raises `RuntimeError` on import if it is unset. No default.
- `ADMIN_API_KEY` — Required by the Altitud Media admin blueprint (`altitud_admin_api.py`); must match the value in the CRM's `platforms.json`
- `PORT` / `FLASK_DEBUG` — local dev only, read by `run-local.sh` from `.env`

## Architecture

Single-file Flask app (`app.py`, ~2350 lines) backed by SQLite, plus a small blueprint in `altitud_admin_api.py`. No ORM — all queries use raw `sqlite3` with `conn.row_factory = sqlite3.Row`. The database is opened per-request via `get_db()` as a context manager.

**Multi-tenancy:** Every workshop (*verkstad*) gets its own `slug` and all vehicles/users are scoped by `verkstad_id`. The root `GET /` route is the public landing page; `GET /<slug>` is the tenant's login entry point that sets `session["verkstad_id"]` before redirecting to `/dashboard`. `check_bil_access()` and `check_aktiv()` are the two key access-control helpers called at the top of most vehicle routes.

**Roles:** `admin` and `anställd`. Admins can manage users within their own `verkstad_id`; superadmin (`session["superadmin"]`) is a separate, global session with its own 30-minute timeout, entirely independent of Flask-Login.

**Schema evolution:** `init_db()` uses `CREATE TABLE IF NOT EXISTS` + bare `ALTER TABLE` calls wrapped in `try/except` to apply incremental migrations idempotently. No migration framework is used. Indexes are created last, because the table-rebuild migration for `bilar` drops the table (and its indexes) the first time it runs.

**Table-rebuild migrations must be guarded.** The `bilar` rebuild (adding `UNIQUE(regnr, verkstad_id)`) checks `sqlite_master.sql` for the constraint before running. Without that guard it re-ran on every startup, dropping and recreating the live vehicle table each boot. Any future rebuild-style migration needs the same kind of "already applied?" check — `try/except` alone does not make a `DROP TABLE` idempotent.

**Service types** are per-workshop rows in `servicetyper` (`kategori='service'`), editable under `/admin`. `har_intervall=1` marks types that get a km countdown; `standard_km` is the workshop's default interval for that type. `sakerstall_servicetyper_seedade()` copies the hard-coded `SERVICE_TYPER` / `NEDRAKNARE_TYPER` lists into the table on first visit to `/admin`, after which those constants are only a fallback.

**Service interval logic:**
1. Per-vehicle overrides in `serviceintervall` table
2. Workshop-specific vehicle model templates in `fordonsmodeller` / `fordonsmodell_intervall`
3. Hard-coded `STANDARD_INTERVALL` dict as final fallback

`bygg_panel()` computes countdown data for each service type by diffing the latest odometer reading against the last time that service type appeared in `handelser`. `/kommande` and `/arbetsorder` each reimplement this same logic inline against preloaded data to avoid N+1 queries — **three copies total**, so interval rule changes must be applied to all three.

**Work-order margin:** `get_arbetsorder_marginal()` returns the km threshold before an interval is reached at which a vehicle shows as "caution" on `/kommande`. Stored per workshop in `verkstader.arbetsorder_marginal_km`, set under `/admin`, defaulting to `ARBETSORDER_MARGINAL_STANDARD` (5000).

**Package limits:** `get_paket_limits()` reads from the `paketinstallningar` table (editable by superadmin at `/superadmin/paket`). It falls back to hardcoded defaults if the table is empty.

**Backups:** `daglig_backup()` runs in a daemon thread, writing per-workshop CSV files to `BACKUP_DIR/<slug>/<date>.csv` once per day. The superadmin panel can trigger a manual backup via `POST /superadmin/backup`.

**Email:** `send_email()` posts directly to the Resend HTTP API using `urllib.request` (no third-party mail library). Welcome emails are sent when a new workshop is created via `/superadmin/ny`.

**Security:** CSRF protection via Flask-WTF on all POST forms. Brute-force protection via in-memory `_login_attempts` / `_sa_login_attempts` dicts (5 attempts, 15-minute lockout) — note this is per-process, so the effective limit multiplies by the Gunicorn worker count. Security headers set globally in `@app.after_request`. All passwords hashed with `pbkdf2:sha256` explicitly (not the default scrypt, for Azure compatibility).

**Session invalidation:** `anvandare.session_token` is mirrored into `session["session_token"]` at login and checked on every request by the `validate_session_token` before-request hook. Every password change (`/mitt-konto`, `/admin/byt-losenord`, `/superadmin/byt-losenord`) must write a **fresh** token via `ny_session_token()` in the same `UPDATE` as the hash. Never set it to `NULL` — legacy sessions also carry `None`, so `NULL` compares equal and the old session survives the password change.

## Templates

`templates/base.html` is the shared layout inherited by all authenticated views. `superadmin.html` and `superadmin_login.html` are separate layouts with their own dark theme. `landing.html` is served as a raw file (not via Jinja) from the repo root.

## Reserved slugs

Slugs used as URL prefixes that cannot be assigned to a workshop: `bil`, `dashboard`, `kommande`, `arbetsorder`, `fordonsbibliotek`, `importera-miltal`, `exportera`, `login`, `logout`, `admin`, `mitt-konto`, `superadmin`, `static`.
