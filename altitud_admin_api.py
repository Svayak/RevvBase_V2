"""
Altitud Media – admin-API för plattformar (Flask).

Lägg denna fil i din Flask-app (t.ex. bredvid app.py), registrera den, och
Altitud Media CRM kan då hantera plattformens konton (tenants) live.

Registrera i din app.py:
    from altitud_admin_api import admin_api
    app.register_blueprint(admin_api)

Sätt en API-nyckel (samma värde läggs i CRM:ets platforms.json):
    export ADMIN_API_KEY="en-lang-slumpad-nyckel"

Anpassa CONFIG nedan efter varje plattforms databas. Standardvärdena matchar
RevvBase (tabell: verkstader). För Scanny/Strykr: ändra tabell- och kolumnnamn.
"""

import os
import sqlite3
from datetime import date
from functools import wraps
from flask import Blueprint, request, jsonify

try:
    from werkzeug.security import generate_password_hash
except Exception:  # om werkzeug saknas fungerar allt utom användarskapande
    generate_password_hash = None

# ------------------------------------------------------------------
# KONFIGURATION – anpassa per plattform
# ------------------------------------------------------------------
CONFIG = {
    "platform_name": "RevvBase",
    "tenant_label": "Verkstäder",
    "db_path": os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "verkstad.db")),

    # Tenant-tabellen och hur dess kolumner mappas till CRM:ets fält
    "tenant_table": "verkstader",
    "cols": {
        "id": "id",
        "name": "namn",
        "slug": "slug",
        "email": "admin_email",
        "plan": "paket",
        "status": "status",
        "created": "skapad",
    },
    "status_active": "aktiv",
    "status_paused": "pausad",
    "default_plan": "bas",

    # Räkna relaterade rader per tenant (valfritt – sätt till None om det inte finns)
    "count_users": {"table": "anvandare", "fk": "verkstad_id"},
    "count_items": {"table": "bilar", "fk": "verkstad_id"},

    # När en tenant skapas: skapa även en admin-användare (valfritt – None för att hoppa över)
    "create_user": {
        "table": "anvandare",
        "fk": "verkstad_id",
        "columns": {  # kolumn -> källa ("username"|"name"|"password_hash"|"role"|literal:VALUE)
            "username": "email",
            "namn": "name",
            "password_hash": "password_hash",
            "roll": "literal:admin",
        },
    },
}

ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")

admin_api = Blueprint("admin_api", __name__)


def _db():
    conn = sqlite3.connect(CONFIG["db_path"])
    conn.row_factory = sqlite3.Row
    return conn


def require_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        key = request.headers.get("X-Admin-Key", "")
        if not ADMIN_API_KEY or key != ADMIN_API_KEY:
            return jsonify({"error": "Ogiltig eller saknad API-nyckel"}), 401
        return fn(*args, **kwargs)
    return wrapper


def _count(conn, spec, tenant_id):
    if not spec:
        return None
    try:
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM {spec['table']} WHERE {spec['fk']} = ?", (tenant_id,)
        ).fetchone()
        return row["n"]
    except Exception:
        return None


@admin_api.route("/api/admin/summary")
@require_key
def summary():
    c = CONFIG["cols"]
    conn = _db()
    try:
        rows = conn.execute(f"SELECT * FROM {CONFIG['tenant_table']}").fetchall()
        tenants = []
        plans = {}
        active = paused = 0
        for r in rows:
            status = r[c["status"]]
            plan = r[c["plan"]] if c["plan"] in r.keys() else None
            if status == CONFIG["status_active"]:
                active += 1
            elif status == CONFIG["status_paused"]:
                paused += 1
            if plan:
                plans[plan] = plans.get(plan, 0) + 1
            tid = r[c["id"]]
            tenants.append({
                "id": tid,
                "name": r[c["name"]],
                "slug": r[c["slug"]] if c["slug"] in r.keys() else None,
                "email": r[c["email"]] if c["email"] in r.keys() else None,
                "plan": plan,
                "status": status,
                "created": r[c["created"]] if c["created"] in r.keys() else None,
                "users": _count(conn, CONFIG.get("count_users"), tid),
                "items": _count(conn, CONFIG.get("count_items"), tid),
            })
        return jsonify({
            "platform": CONFIG["platform_name"],
            "tenantLabel": CONFIG["tenant_label"],
            "stats": {"total": len(rows), "active": active, "paused": paused, "plans": plans},
            "tenants": tenants,
        })
    finally:
        conn.close()


@admin_api.route("/api/admin/tenants", methods=["POST"])
@require_key
def create_tenant():
    c = CONFIG["cols"]
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or "").strip().lower().replace(" ", "-")
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    plan = (data.get("plan") or CONFIG["default_plan"]).strip()
    if not (name and slug and email):
        return jsonify({"error": "Namn, slug och e-post krävs"}), 400

    conn = _db()
    try:
        cur = conn.execute(
            f"INSERT INTO {CONFIG['tenant_table']} "
            f"({c['name']}, {c['slug']}, {c['email']}, {c['plan']}, {c['status']}, {c['created']}) "
            f"VALUES (?,?,?,?,?,?)",
            (name, slug, email, plan, CONFIG["status_active"], str(date.today())),
        )
        tenant_id = cur.lastrowid

        cu = CONFIG.get("create_user")
        if cu and password and generate_password_hash:
            cols, vals = [cu["fk"]], [tenant_id]
            sources = {
                "email": email, "name": name,
                "password_hash": generate_password_hash(password),
            }
            for col, src in cu["columns"].items():
                cols.append(col)
                if src.startswith("literal:"):
                    vals.append(src.split("literal:", 1)[1])
                else:
                    vals.append(sources.get(src))
            placeholders = ",".join(["?"] * len(vals))
            conn.execute(
                f"INSERT INTO {cu['table']} ({','.join(cols)}) VALUES ({placeholders})", vals
            )
        conn.commit()
        return jsonify({"id": tenant_id, "created": True})
    except sqlite3.IntegrityError as e:
        return jsonify({"error": f"Kunde inte skapa (finns redan?): {e}"}), 400
    finally:
        conn.close()


@admin_api.route("/api/admin/tenants/<int:tid>/toggle", methods=["POST"])
@require_key
def toggle_tenant(tid):
    c = CONFIG["cols"]
    conn = _db()
    try:
        row = conn.execute(
            f"SELECT {c['status']} AS status FROM {CONFIG['tenant_table']} WHERE {c['id']}=?", (tid,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Hittades inte"}), 404
        new_status = CONFIG["status_paused"] if row["status"] == CONFIG["status_active"] else CONFIG["status_active"]
        conn.execute(
            f"UPDATE {CONFIG['tenant_table']} SET {c['status']}=? WHERE {c['id']}=?", (new_status, tid)
        )
        conn.commit()
        return jsonify({"id": tid, "status": new_status})
    finally:
        conn.close()


@admin_api.route("/api/admin/tenants/<int:tid>", methods=["DELETE"])
@require_key
def delete_tenant(tid):
    c = CONFIG["cols"]
    conn = _db()
    try:
        cu = CONFIG.get("create_user")
        if cu:
            try:
                conn.execute(f"DELETE FROM {cu['table']} WHERE {cu['fk']}=?", (tid,))
            except Exception:
                pass
        conn.execute(f"DELETE FROM {CONFIG['tenant_table']} WHERE {c['id']}=?", (tid,))
        conn.commit()
        return jsonify({"id": tid, "deleted": True})
    finally:
        conn.close()
