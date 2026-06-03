# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
# Development
python app.py           # runs on port 5001

# Production (via Gunicorn)
gunicorn wsgi:app
```

`wsgi.py` is the production entry point — it calls `init_db()`, seeds the default admin user, and starts the background backup thread before handing off to Gunicorn.

Environment variables:
- `SECRET_KEY` — Flask session key (falls back to `.secret_key` file, then auto-generates)
- `DB_PATH` — SQLite database path (default: `verkstad.db` next to `app.py`)
- `BACKUP_DIR` — CSV backup destination (default: `/home/data/säkerhetskopior`)
- `RESEND_API_KEY` — Required for outgoing email via Resend API
- `SUPERADMIN_PASSWORD` — Superadmin panel password (default: `revvbase-super-2026`)

## Architecture

Single-file Flask app (`app.py`, ~1700 lines) backed by SQLite. No ORM — all queries use raw `sqlite3` with `conn.row_factory = sqlite3.Row`. The database is opened per-request via `get_db()` as a context manager.

**Multi-tenancy:** Every workshop (*verkstad*) gets its own `slug` and all vehicles/users are scoped by `verkstad_id`. The root `GET /` route is the public landing page; `GET /<slug>` is the tenant's login entry point that sets `session["verkstad_id"]` before redirecting to `/dashboard`. `check_bil_access()` and `check_aktiv()` are the two key access-control helpers called at the top of most vehicle routes.

**Roles:** `admin` and `anställd`. Admins can manage users within their own `verkstad_id`; superadmin (`session["superadmin"]`) is a separate, global session with its own 30-minute timeout, entirely independent of Flask-Login.

**Schema evolution:** `init_db()` uses `CREATE TABLE IF NOT EXISTS` + bare `ALTER TABLE` calls wrapped in `try/except` to apply incremental migrations idempotently. No migration framework is used.

**Service interval logic:**
1. Per-vehicle overrides in `serviceintervall` table
2. Workshop-specific vehicle model templates in `fordonsmodeller` / `fordonsmodell_intervall`
3. Hard-coded `STANDARD_INTERVALL` dict as final fallback

`bygg_panel()` computes countdown data for each service type by diffing the latest odometer reading against the last time that service type appeared in `handelser`.

**Package limits:** `get_paket_limits()` reads from the `paketinstallningar` table (editable by superadmin at `/superadmin/paket`). It falls back to hardcoded defaults if the table is empty.

**Backups:** `daglig_backup()` runs in a daemon thread, writing per-workshop CSV files to `BACKUP_DIR/<slug>/<date>.csv` once per day. The superadmin panel can trigger a manual backup via `POST /superadmin/backup`.

**Email:** `send_email()` posts directly to the Resend HTTP API using `urllib.request` (no third-party mail library). Welcome emails are sent when a new workshop is created via `/superadmin/ny`.

**Security:** CSRF protection via Flask-WTF on all POST forms. Brute-force protection via in-memory `_login_attempts` / `_sa_login_attempts` dicts (5 attempts, 15-minute lockout). Security headers set globally in `@app.after_request`. All passwords hashed with `pbkdf2:sha256` explicitly (not the default scrypt, for Azure compatibility).

## Templates

`templates/base.html` is the shared layout inherited by all authenticated views. `superadmin.html` and `superadmin_login.html` are separate layouts with their own dark theme. `landing.html` is served as a raw file (not via Jinja) from the repo root.

## Reserved slugs

Slugs used as URL prefixes that cannot be assigned to a workshop: `bil`, `dashboard`, `kommande`, `arbetsorder`, `fordonsbibliotek`, `importera-miltal`, `exportera`, `login`, `logout`, `admin`, `mitt-konto`, `superadmin`, `static`.
