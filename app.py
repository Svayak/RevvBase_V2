from flask import Flask, render_template, request, redirect, url_for, session, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, json, os, csv, threading, time, secrets
from datetime import date, datetime
from collections import defaultdict

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["PERMANENT_SESSION_LIFETIME"] = 8 * 60 * 60
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

_KEY_FILE = os.path.join(os.path.dirname(__file__), ".secret_key")
if os.environ.get("SECRET_KEY"):
    app.secret_key = os.environ.get("SECRET_KEY")
elif os.path.exists(_KEY_FILE):
    with open(_KEY_FILE, "r") as _f:
        app.secret_key = _f.read().strip()
else:
    _new_key = secrets.token_hex(32)
    with open(_KEY_FILE, "w") as _f:
        _f.write(_new_key)
    app.secret_key = _new_key

# FIX #2: DB_PATH defaults to /home/data/verkstad.db on Azure (persistent storage)
# Set DB_PATH=/home/data/verkstad.db in Azure App Service → Configuration → Application settings
DB = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "verkstad.db"))

csrf = CSRFProtect(app)
login_manager = LoginManager()

# ── BRUTE-FORCE SKYDD ────────────────────────────────────────────────────────
_login_attempts = defaultdict(list)
_sa_login_attempts = defaultdict(list)
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60

def check_rate_limit(ip, store=None):
    if store is None:
        store = _login_attempts
    nu = time.time()
    store[ip] = [t for t in store[ip] if nu - t < LOCKOUT_SECONDS]
    if len(store[ip]) >= MAX_ATTEMPTS:
        kvar = int(LOCKOUT_SECONDS - (nu - store[ip][0]))
        return True, kvar
    return False, 0

def registrera_misslyckat(ip, store=None):
    if store is None:
        store = _login_attempts
    store[ip].append(time.time())

def rensa_forsok(ip, store=None):
    if store is None:
        store = _login_attempts
    store.pop(ip, None)

# ── LOGIN MANAGER ─────────────────────────────────────────────────────────────
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Logga in för att fortsätta."

class User(UserMixin):
    def __init__(self, id, username, namn, roll, verkstad_id, slug=None):
        self.id = id
        self.username = username
        self.namn = namn
        self.roll = roll
        self.verkstad_id = verkstad_id
        self.slug = slug

@login_manager.user_loader
def load_user(user_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM anvandare WHERE id=?", (user_id,)).fetchone()
        if not row:
            return None
        slug = None
        if row["verkstad_id"]:
            v = conn.execute("SELECT slug FROM verkstader WHERE id=?", (row["verkstad_id"],)).fetchone()
            slug = v["slug"] if v else None
    return User(row["id"], row["username"], row["namn"], row["roll"], row["verkstad_id"], slug)

# ── HJÄLPFUNKTIONER ───────────────────────────────────────────────────────────
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "säkerhetskopior")

SERVICE_TYPER = [
    "Oljebyte", "Kamrem",
    "Bromsklossar fram", "Bromsklossar bak",
    "Bromsskivor fram", "Bromsskivor bak",
    "Luftfilter", "Kylvätska",
    "Tändstift", "Drivrem",
    "Däckbyte", "Bromsvätska",
    "Pollenfilter", "Växellådsolja",
]

NEDRAKNARE_TYPER = [
    "Oljebyte", "Kamrem",
    "Bromsklossar fram", "Bromsklossar bak",
    "Bromsskivor fram", "Bromsskivor bak",
    "Luftfilter", "Kylvätska",
]

STANDARD_INTERVALL = {
    "Ford Transit": {
        "Oljebyte": 15000, "Kamrem": 100000,
        "Bromsklossar fram": 30000, "Bromsklossar bak": 40000,
        "Bromsskivor fram": 60000, "Bromsskivor bak": 80000,
        "Luftfilter": 30000, "Kylvätska": 100000,
    },
    "Renault Master": {
        "Oljebyte": 18000, "Kamrem": 100000,
        "Bromsklossar fram": 30000, "Bromsklossar bak": 40000,
        "Bromsskivor fram": 60000, "Bromsskivor bak": 80000,
        "Luftfilter": 30000, "Kylvätska": 100000,
    },
    "Opel Movano": {
        "Oljebyte": 25000, "Kamrem": None,
        "Bromsklossar fram": 30000, "Bromsklossar bak": 40000,
        "Bromsskivor fram": 60000, "Bromsskivor bak": 80000,
        "Luftfilter": 30000, "Kylvätska": 100000,
    },
    "Renault Scénic": {
        "Oljebyte": 18000, "Kamrem": 100000,
        "Bromsklossar fram": 30000, "Bromsklossar bak": 40000,
        "Bromsskivor fram": 60000, "Bromsskivor bak": 80000,
        "Luftfilter": 30000, "Kylvätska": 100000,
    },
}

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def check_bil_access(bil_id):
    with get_db() as conn:
        b = conn.execute("SELECT * FROM bilar WHERE id=?", (bil_id,)).fetchone()
    if not b:
        abort(404)
    if current_user.verkstad_id is not None and b["verkstad_id"] != current_user.verkstad_id:
        abort(403)
    return b

def get_verkstad_status():
    if current_user.verkstad_id is None:
        return "aktiv"
    with get_db() as conn:
        v = conn.execute("SELECT status FROM verkstader WHERE id=?", (current_user.verkstad_id,)).fetchone()
    return v["status"] if v else "aktiv"

def check_aktiv():
    if get_verkstad_status() == "pausad":
        return render_template("pausad.html")
    return None

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bilar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                regnr TEXT NOT NULL UNIQUE,
                fordonsnummer TEXT,
                marke TEXT NOT NULL,
                modell TEXT NOT NULL,
                arsmodell INTEGER,
                notering TEXT
            );
            CREATE TABLE IF NOT EXISTS handelser (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bil_id INTEGER NOT NULL,
                datum TEXT NOT NULL,
                km INTEGER NOT NULL,
                typ TEXT NOT NULL,
                service_typer TEXT,
                beskrivning TEXT,
                FOREIGN KEY (bil_id) REFERENCES bilar(id)
            );
            CREATE TABLE IF NOT EXISTS serviceintervall (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bil_id INTEGER NOT NULL,
                service_typ TEXT NOT NULL,
                intervall_km INTEGER,
                aktiv INTEGER NOT NULL DEFAULT 1,
                UNIQUE(bil_id, service_typ),
                FOREIGN KEY (bil_id) REFERENCES bilar(id)
            );
        """)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS anvandare (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                namn TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                roll TEXT NOT NULL DEFAULT 'anställd'
            );
        """)
        try:
            conn.execute("ALTER TABLE handelser ADD COLUMN skapad_av TEXT")
        except: pass
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS fordonsmodeller (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marke TEXT NOT NULL,
                modell TEXT NOT NULL,
                arsmodell INTEGER,
                UNIQUE(marke, modell, arsmodell)
            );
            CREATE TABLE IF NOT EXISTS fordonsmodell_intervall (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fordonsmodell_id INTEGER NOT NULL,
                service_typ TEXT NOT NULL,
                intervall_km INTEGER,
                aktiv INTEGER NOT NULL DEFAULT 1,
                UNIQUE(fordonsmodell_id, service_typ),
                FOREIGN KEY (fordonsmodell_id) REFERENCES fordonsmodeller(id)
            );
        """)
        try:
            conn.execute("ALTER TABLE handelser RENAME COLUMN miltal TO km")
        except: pass
        try:
            conn.execute("ALTER TABLE bilar ADD COLUMN fordonsnummer TEXT")
        except: pass
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS kommentarer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bil_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                skapad_av TEXT,
                datum TEXT NOT NULL,
                FOREIGN KEY (bil_id) REFERENCES bilar(id)
            );
            CREATE TABLE IF NOT EXISTS verkstader (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namn TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                admin_email TEXT NOT NULL,
                paket TEXT NOT NULL DEFAULT 'bas',
                status TEXT NOT NULL DEFAULT 'aktiv',
                skapad TEXT NOT NULL
            );
        """)
        try:
            conn.execute("ALTER TABLE anvandare ADD COLUMN verkstad_id INTEGER")
        except: pass
        try:
            conn.execute("ALTER TABLE bilar ADD COLUMN verkstad_id INTEGER")
        except: pass
        try:
            conn.execute("ALTER TABLE bilar ADD COLUMN verkstad_id INTEGER")
        except: pass
        try:
            conn.execute("ALTER TABLE anvandare ADD COLUMN senaste_inloggning TEXT")
        except: pass

def get_fordonsmodell_intervall(marke, modell, arsmodell):
    with get_db() as conn:
        fm = conn.execute(
            "SELECT id FROM fordonsmodeller WHERE marke=? AND modell=? AND (arsmodell=? OR arsmodell IS NULL) ORDER BY arsmodell DESC LIMIT 1",
            (marke, modell, arsmodell)
        ).fetchone()
        if not fm:
            return {}
        rader = conn.execute(
            "SELECT service_typ, intervall_km, aktiv FROM fordonsmodell_intervall WHERE fordonsmodell_id=?",
            (fm["id"],)
        ).fetchall()
    return {r["service_typ"]: {"intervall": r["intervall_km"], "aktiv": bool(r["aktiv"])} for r in rader}

def get_intervall(bil_id, marke, modell, arsmodell=None):
    nyckel = f"{marke} {modell}"
    fm_intervall = get_fordonsmodell_intervall(marke, modell, arsmodell)
    standard = fm_intervall if fm_intervall else STANDARD_INTERVALL.get(nyckel, {})
    with get_db() as conn:
        rader = conn.execute(
            "SELECT service_typ, intervall_km, aktiv FROM serviceintervall WHERE bil_id=?", (bil_id,)
        ).fetchall()
    result = {}
    db_map = {r["service_typ"]: r for r in rader}
    for t in NEDRAKNARE_TYPER:
        if t in db_map:
            r = db_map[t]
            result[t] = {"intervall": r["intervall_km"], "aktiv": bool(r["aktiv"]), "egen": False}
        elif rader:
            pass
        elif t in standard:
            result[t] = {"intervall": standard[t], "aktiv": standard[t] is not None, "egen": False}
    for r in rader:
        if r["service_typ"] not in NEDRAKNARE_TYPER and bool(r["aktiv"]):
            result[r["service_typ"]] = {"intervall": r["intervall_km"], "aktiv": True, "egen": True}
    return result

def spara_intervall(bil_id, intervall_dict):
    with get_db() as conn:
        egna_nya = [t for t, v in intervall_dict.items() if v.get("egen")]
        befintliga_egna = conn.execute(
            "SELECT service_typ FROM serviceintervall WHERE bil_id=? AND service_typ NOT IN ({})".format(
                ",".join("?" * len(NEDRAKNARE_TYPER))
            ), [bil_id] + NEDRAKNARE_TYPER
        ).fetchall()
        for r in befintliga_egna:
            if r["service_typ"] not in egna_nya:
                conn.execute("DELETE FROM serviceintervall WHERE bil_id=? AND service_typ=?", (bil_id, r["service_typ"]))
        for typ, info in intervall_dict.items():
            conn.execute("""
                INSERT INTO serviceintervall (bil_id, service_typ, intervall_km, aktiv)
                VALUES (?,?,?,?)
                ON CONFLICT(bil_id, service_typ) DO UPDATE SET intervall_km=excluded.intervall_km, aktiv=excluded.aktiv
            """, (bil_id, typ, info.get("intervall"), 1 if info.get("aktiv") else 0))

def bygg_panel(bil_id, marke, modell, handelser, senaste_km, arsmodell=None):
    intervaller = get_intervall(bil_id, marke, modell, arsmodell)
    senaste_per_typ = {}
    for h in handelser:
        if h["service_typer"]:
            for t in json.loads(h["service_typer"]):
                if t not in senaste_per_typ:
                    senaste_per_typ[t] = h["km"]
    panel = {}
    for t, info in intervaller.items():
        if not info["aktiv"]:
            continue
        iv = info["intervall"]
        if t in senaste_per_typ:
            diff = (senaste_km - senaste_per_typ[t]) if senaste_km is not None else None
            aldrig_gjort = False
        else:
            diff = senaste_km if senaste_km is not None else None
            aldrig_gjort = True
        panel[t] = {"diff": diff, "intervall": iv, "aldrig_gjort": aldrig_gjort}
    return panel

def daglig_backup():
    while True:
        nu = datetime.now()
        idag = nu.strftime("%Y-%m-%d")
        try:
            with get_db() as conn:
                verkstader = conn.execute("SELECT id, slug FROM verkstader").fetchall()
            for v in verkstader:
                slug = v["slug"]
                verkstad_id = v["id"]
                mapp = os.path.join(BACKUP_DIR, slug)
                os.makedirs(mapp, exist_ok=True)
                fil = os.path.join(mapp, f"{idag}.csv")
                if not os.path.exists(fil):
                    try:
                        with get_db() as conn:
                            bilar = conn.execute(
                                "SELECT id, regnr, fordonsnummer, marke, modell, arsmodell, notering FROM bilar WHERE verkstad_id = ?",
                                (verkstad_id,)
                            ).fetchall()
                            handelser = conn.execute("""
                                SELECT h.*, b.regnr, b.fordonsnummer, b.marke, b.modell
                                FROM handelser h
                                JOIN bilar b ON h.bil_id = b.id
                                WHERE b.verkstad_id = ?
                            """, (verkstad_id,)).fetchall()
                        with open(fil, "w", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f)
                            writer.writerow(["## BILAR"])
                            writer.writerow(["id","regnr","fordonsnummer","marke","modell","arsmodell","notering"])
                            for b in bilar:
                                writer.writerow([
                                    b["id"], b["regnr"], b["fordonsnummer"],
                                    b["marke"], b["modell"], b["arsmodell"], b["notering"]
                                ])
                            writer.writerow([])
                            writer.writerow(["## HÄNDELSER"])
                            writer.writerow(["id","bil_id","regnr","fordonsnummer","marke","modell","datum","km","typ","service_typer","beskrivning"])
                            for h in handelser:
                                writer.writerow([
                                    h["id"], h["bil_id"],
                                    h["regnr"], h["fordonsnummer"], h["marke"], h["modell"],
                                    h["datum"], h["km"], h["typ"],
                                    h["service_typer"], h["beskrivning"]
                                ])
                    except Exception as e:
                        print(f"Backup fel ({slug}): {e}")
        except Exception as e:
            print(f"Backup fel (verkstadslista): {e}")
        time.sleep(3600)

# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    # FIX #1: Use absolute path so it works regardless of gunicorn working directory
    landing_path = os.path.join(os.path.dirname(__file__), "landing.html")
    return open(landing_path, encoding="utf-8").read()

RESERVERADE_SLUGS = {
    "bil", "dashboard", "kommande", "arbetsorder", "fordonsbibliotek",
    "importera-miltal", "exportera", "login", "logout", "admin",
    "mitt-konto", "superadmin", "static"
}

@app.route("/<slug>")
@login_required
def slug_dashboard(slug):
    if slug in RESERVERADE_SLUGS:
        return redirect(url_for("index"))
    pausad = check_aktiv()
    if pausad:
        return pausad
    with get_db() as conn:
        v = conn.execute("SELECT id FROM verkstader WHERE slug=?", (slug,)).fetchone()
    if not v:
        return redirect(url_for("index"))
    if current_user.verkstad_id is not None and current_user.verkstad_id != v["id"]:
        if current_user.slug:
            return redirect(f"/{current_user.slug}")
        return redirect(url_for("index"))
    q = request.args.get("q", "").strip()
    vid = current_user.verkstad_id
    with get_db() as conn:
        if q:
            if vid is not None:
                bilar = conn.execute(
                    "SELECT * FROM bilar WHERE verkstad_id=? AND (regnr LIKE ? OR marke LIKE ? OR modell LIKE ? OR fordonsnummer LIKE ? OR notering LIKE ?) ORDER BY regnr",
                    (vid, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%")
                ).fetchall()
            else:
                bilar = conn.execute(
                    "SELECT * FROM bilar WHERE regnr LIKE ? OR marke LIKE ? OR modell LIKE ? OR fordonsnummer LIKE ? OR notering LIKE ? ORDER BY regnr",
                    (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%")
                ).fetchall()
        else:
            if vid is not None:
                bilar = conn.execute(
                    "SELECT * FROM bilar WHERE verkstad_id=? ORDER BY fordonsnummer, regnr", (vid,)
                ).fetchall()
            else:
                bilar = conn.execute(
                    "SELECT * FROM bilar ORDER BY fordonsnummer, regnr"
                ).fetchall()
    return render_template("index.html", bilar=bilar, q=q)

@app.route("/dashboard")
@login_required
def index():
    if current_user.slug:
        return redirect(f"/{current_user.slug}")
    pausad = check_aktiv()
    if pausad:
        return pausad
    q = request.args.get("q", "").strip()
    vid = current_user.verkstad_id
    # FIX #3: Explicit SQL instead of fragile .replace() pattern
    with get_db() as conn:
        if q:
            if vid is not None:
                bilar = conn.execute(
                    "SELECT * FROM bilar WHERE verkstad_id=? AND (regnr LIKE ? OR marke LIKE ? OR modell LIKE ? OR fordonsnummer LIKE ? OR notering LIKE ?) ORDER BY regnr",
                    (vid, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%")
                ).fetchall()
            else:
                bilar = conn.execute(
                    "SELECT * FROM bilar WHERE regnr LIKE ? OR marke LIKE ? OR modell LIKE ? OR fordonsnummer LIKE ? OR notering LIKE ? ORDER BY regnr",
                    (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%")
                ).fetchall()
        else:
            if vid is not None:
                bilar = conn.execute(
                    "SELECT * FROM bilar WHERE verkstad_id=? ORDER BY fordonsnummer, regnr", (vid,)
                ).fetchall()
            else:
                bilar = conn.execute(
                    "SELECT * FROM bilar ORDER BY fordonsnummer, regnr"
                ).fetchall()
    return render_template("index.html", bilar=bilar, q=q)

@app.route("/bil/ny", methods=["GET","POST"])
@login_required
def ny_bil():
    pausad = check_aktiv()
    if pausad:
        return pausad
    error = None
    with get_db() as conn:
        bibliotek = conn.execute(
            "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell"
        ).fetchall()

    if request.method == "POST":
        regnr         = request.form.get("regnr","").strip().upper()
        fordonsnummer = request.form.get("fordonsnummer","").strip()
        marke         = request.form.get("marke","").strip()
        modell        = request.form.get("modell","").strip()
        arsmodell     = request.form.get("arsmodell","").strip()
        notering      = request.form.get("notering","").strip()

        if not regnr or not marke or not modell:
            error = "Reg.nr, märke och modell är obligatoriska."
        else:
            # Kontrollera fordonskvot
            if current_user.verkstad_id is not None:
                PAKET_FORDON = {"bas": 25, "standard": 100, "pro": 9999}
                with get_db() as conn:
                    v = conn.execute("SELECT paket FROM verkstader WHERE id=?", (current_user.verkstad_id,)).fetchone()
                    paket = v["paket"] if v else "bas"
                    antal = conn.execute("SELECT COUNT(*) FROM bilar WHERE verkstad_id=?", (current_user.verkstad_id,)).fetchone()[0]
                max_fordon = PAKET_FORDON.get(paket, 25)
                if antal >= max_fordon:
                    error = f"Paketet {paket.capitalize()} tillåter max {max_fordon} fordon. Uppgradera för att lägga till fler."

            if not error:
                vid = current_user.verkstad_id
                ar = int(arsmodell) if arsmodell.isdigit() else None
                try:
                    # INSERT bil
                    with get_db() as conn:
                        cur = conn.execute(
                            "INSERT INTO bilar (regnr,fordonsnummer,marke,modell,arsmodell,notering,verkstad_id) VALUES (?,?,?,?,?,?,?)",
                            (regnr, fordonsnummer or None, marke, modell, ar, notering or None, vid)
                        )
                        bil_id = cur.lastrowid

                    # Bygg intervall-dict från formuläret
                    iv_dict = {}
                    for t in NEDRAKNARE_TYPER:
                        aktiv = request.form.get(f"aktiv_{t}") == "1"
                        iv_str = request.form.get(f"iv_{t}", "").strip()
                        iv_km = int(iv_str) if iv_str.isdigit() else None
                        iv_dict[t] = {"intervall": iv_km, "aktiv": aktiv, "egen": False}
                    egna_namn = request.form.getlist("egen_namn")
                    egna_km   = request.form.getlist("egen_km")
                    for namn, km_str in zip(egna_namn, egna_km):
                        namn = namn.strip()
                        if namn and km_str.strip().isdigit():
                            iv_dict[namn] = {"intervall": int(km_str), "aktiv": True, "egen": True}
                    spara_intervall(bil_id, iv_dict)

                    # FIX #4: Spara fordonsmodell med en enda connection istället för en per loop-iteration
                    with get_db() as conn:
                        befintlig = conn.execute(
                            "SELECT id FROM fordonsmodeller WHERE marke=? AND modell=? AND (arsmodell=? OR (arsmodell IS NULL AND ? IS NULL))",
                            (marke, modell, ar, ar)
                        ).fetchone()
                        if not befintlig:
                            cur2 = conn.execute(
                                "INSERT INTO fordonsmodeller (marke, modell, arsmodell) VALUES (?,?,?)",
                                (marke, modell, ar)
                            )
                            fm_id = cur2.lastrowid
                            for t, info in iv_dict.items():
                                conn.execute(
                                    "INSERT OR REPLACE INTO fordonsmodell_intervall (fordonsmodell_id, service_typ, intervall_km, aktiv) VALUES (?,?,?,?)",
                                    (fm_id, t, info.get("intervall"), 1 if info.get("aktiv") else 0)
                                )

                    return redirect(url_for("index"))
                except sqlite3.IntegrityError:
                    error = f"Reg.nr {regnr} finns redan i systemet."

    return render_template("ny_bil.html", error=error,
        nedraknare_typer=NEDRAKNARE_TYPER, bibliotek=bibliotek)

@app.route("/bil/<int:bil_id>")
@login_required
def bil(bil_id):
    b = check_bil_access(bil_id)
    filter_typ = request.args.get("filter", "").strip()
    with get_db() as conn:
        if filter_typ:
            handelser = conn.execute(
                "SELECT * FROM handelser WHERE bil_id=? AND service_typer LIKE ? ORDER BY km DESC, datum DESC",
                (bil_id, f"%{filter_typ}%")
            ).fetchall()
        else:
            handelser = conn.execute(
                "SELECT * FROM handelser WHERE bil_id=? ORDER BY km DESC, datum DESC", (bil_id,)
            ).fetchall()
        alla_handelser = conn.execute(
            "SELECT * FROM handelser WHERE bil_id=? ORDER BY km DESC", (bil_id,)
        ).fetchall()
        kommentarer = conn.execute(
            "SELECT * FROM kommentarer WHERE bil_id=? ORDER BY id DESC", (bil_id,)
        ).fetchall()

    senaste_km = alla_handelser[0]["km"] if alla_handelser else None
    panel = bygg_panel(bil_id, b["marke"], b["modell"], alla_handelser, senaste_km)
    return render_template("bil.html", bil=b, handelser=handelser,
        panel=panel, senaste_km=senaste_km,
        service_typer=SERVICE_TYPER, filter_typ=filter_typ,
        kommentarer=kommentarer)

@app.route("/bil/<int:bil_id>/redigera", methods=["GET","POST"])
@login_required
def redigera_bil(bil_id):
    b = check_bil_access(bil_id)
    intervaller = get_intervall(bil_id, b["marke"], b["modell"])
    error = None
    if request.method == "POST":
        marke         = request.form.get("marke","").strip()
        modell        = request.form.get("modell","").strip()
        fordonsnummer = request.form.get("fordonsnummer","").strip()
        arsmodell     = request.form.get("arsmodell","").strip()
        notering      = request.form.get("notering","").strip()
        if not marke or not modell:
            error = "Märke och modell är obligatoriska."
        else:
            with get_db() as conn:
                conn.execute(
                    "UPDATE bilar SET marke=?,modell=?,fordonsnummer=?,arsmodell=?,notering=? WHERE id=?",
                    (marke, modell, fordonsnummer or None, arsmodell or None, notering, bil_id)
                )
            iv_dict = {}
            for t in NEDRAKNARE_TYPER:
                aktiv = request.form.get(f"aktiv_{t}") == "1"
                iv_str = request.form.get(f"iv_{t}", "").strip()
                iv_km = int(iv_str) if iv_str.isdigit() else None
                iv_dict[t] = {"intervall": iv_km, "aktiv": aktiv, "egen": False}
            egna_namn = request.form.getlist("egen_namn")
            egna_km   = request.form.getlist("egen_km")
            for namn, km_str in zip(egna_namn, egna_km):
                namn = namn.strip()
                if namn and km_str.strip().isdigit():
                    iv_dict[namn] = {"intervall": int(km_str), "aktiv": True, "egen": True}
            spara_intervall(bil_id, iv_dict)
            return redirect(url_for("bil", bil_id=bil_id))
    return render_template("redigera_bil.html", bil=b, error=error,
        intervaller=intervaller, nedraknare_typer=NEDRAKNARE_TYPER)

@app.route("/bil/<int:bil_id>/ny-handelse", methods=["GET","POST"])
@login_required
def ny_handelse(bil_id):
    b = check_bil_access(bil_id)
    intervaller = get_intervall(bil_id, b["marke"], b["modell"])
    egna_typer = [t for t in intervaller if t not in NEDRAKNARE_TYPER and intervaller[t].get("aktiv")]
    alla_service_typer = SERVICE_TYPER + [t for t in egna_typer if t not in SERVICE_TYPER]
    steg = request.args.get("steg", "1")
    km   = request.args.get("km", "")
    error = None

    if request.method == "POST":
        steg = request.form.get("steg","1")
        km   = request.form.get("km","").strip()

        if steg == "1":
            if not km or not km.isdigit():
                error = "Ange ett giltigt kilometertal."
                return render_template("ny_handelse.html", bil=b, steg="1", km="", error=error, service_typer=alla_service_typer)
            return redirect(url_for("ny_handelse", bil_id=bil_id, steg="2", km=km))

        elif steg == "2":
            typ = request.form.get("typ","")
            if typ not in ("service","fel","miltal"):
                error = "Välj typ av händelse."
                return render_template("ny_handelse.html", bil=b, steg="2", km=km, error=error, service_typer=alla_service_typer)
            if typ == "miltal":
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO handelser (bil_id,datum,km,typ,service_typer,beskrivning,skapad_av) VALUES (?,?,?,?,?,?,?)",
                        (bil_id, str(date.today()), int(km), "miltal", None, None, current_user.namn)
                    )
                return redirect(url_for("bil", bil_id=bil_id))
            return redirect(url_for("ny_handelse", bil_id=bil_id, steg="3", km=km, typ=typ))

        elif steg == "3":
            typ = request.form.get("typ","")
            datum = request.form.get("datum", str(date.today()))
            beskrivning = request.form.get("beskrivning","").strip()
            service_typer_vald = request.form.getlist("service_typer")
            if typ == "service" and not service_typer_vald:
                error = "Välj minst en serviceåtgärd."
                return render_template("ny_handelse.html", bil=b, steg="3", km=km, typ=typ,
                    error=error, service_typer=alla_service_typer, today=str(date.today()))
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO handelser (bil_id,datum,km,typ,service_typer,beskrivning,skapad_av) VALUES (?,?,?,?,?,?,?)",
                    (bil_id, datum, int(km), typ,
                     json.dumps(service_typer_vald) if service_typer_vald else None,
                     beskrivning or None, current_user.namn)
                )
            return redirect(url_for("bil", bil_id=bil_id))

    return render_template("ny_handelse.html", bil=b, steg=steg, km=km,
        error=error, service_typer=alla_service_typer, typ=request.args.get("typ",""),
        today=str(date.today()))

@app.route("/bil/<int:bil_id>/redigera-handelse/<int:h_id>", methods=["GET","POST"])
@login_required
def redigera_handelse(bil_id, h_id):
    b = check_bil_access(bil_id)
    with get_db() as conn:
        h = conn.execute("SELECT * FROM handelser WHERE id=? AND bil_id=?", (h_id, bil_id)).fetchone()
    if not h:
        return redirect(url_for("bil", bil_id=bil_id))
    error = None
    service_typer_vald = json.loads(h["service_typer"]) if h["service_typer"] else []

    if request.method == "POST":
        datum = request.form.get("datum","").strip()
        km_str = request.form.get("km","").strip()
        beskrivning = request.form.get("beskrivning","").strip()
        service_typer_ny = request.form.getlist("service_typer")
        if not km_str.isdigit():
            error = "Ange ett giltigt kilometertal."
        else:
            with get_db() as conn:
                conn.execute(
                    "UPDATE handelser SET datum=?,km=?,service_typer=?,beskrivning=? WHERE id=? AND bil_id=?",
                    (datum, int(km_str),
                     json.dumps(service_typer_ny) if service_typer_ny else None,
                     beskrivning or None, h_id, bil_id)
                )
            return redirect(url_for("bil", bil_id=bil_id))

    return render_template("redigera_handelse.html", bil=b, h=h,
        service_typer=SERVICE_TYPER, service_typer_vald=service_typer_vald, error=error)

@app.route("/bil/<int:bil_id>/ny-kommentar", methods=["POST"])
@login_required
def ny_kommentar(bil_id):
    check_bil_access(bil_id)
    text = request.form.get("text", "").strip()
    if text:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO kommentarer (bil_id, text, skapad_av, datum) VALUES (?,?,?,?)",
                (bil_id, text, current_user.namn, str(date.today()))
            )
    return redirect(url_for("bil", bil_id=bil_id))

@app.route("/bil/<int:bil_id>/ta-bort-kommentar/<int:k_id>", methods=["POST"])
@login_required
def ta_bort_kommentar(bil_id, k_id):
    check_bil_access(bil_id)
    with get_db() as conn:
        conn.execute("DELETE FROM kommentarer WHERE id=? AND bil_id=?", (k_id, bil_id))
    return redirect(url_for("bil", bil_id=bil_id))

@app.route("/bil/<int:bil_id>/ta-bort-handelse/<int:h_id>", methods=["POST"])
@login_required
def ta_bort_handelse(bil_id, h_id):
    check_bil_access(bil_id)
    with get_db() as conn:
        conn.execute("DELETE FROM handelser WHERE id=? AND bil_id=?", (h_id, bil_id))
    return redirect(url_for("bil", bil_id=bil_id))

@app.route("/bil/<int:bil_id>/ta-bort", methods=["POST"])
@login_required
def ta_bort_bil(bil_id):
    check_bil_access(bil_id)
    with get_db() as conn:
        conn.execute("DELETE FROM handelser WHERE bil_id=?", (bil_id,))
        conn.execute("DELETE FROM serviceintervall WHERE bil_id=?", (bil_id,))
        conn.execute("DELETE FROM kommentarer WHERE bil_id=?", (bil_id,))
        conn.execute("DELETE FROM bilar WHERE id=?", (bil_id,))
    return redirect(url_for("index"))

@app.route("/bil/<int:bil_id>/print")
@login_required
def print_bil(bil_id):
    b = check_bil_access(bil_id)
    with get_db() as conn:
        handelser = conn.execute(
            "SELECT * FROM handelser WHERE bil_id=? ORDER BY km DESC", (bil_id,)
        ).fetchall()
    return render_template("print_bil.html", bil=b, handelser=handelser, today=str(date.today()))

@app.route("/kommande")
@login_required
def kommande():
    pausad = check_aktiv()
    if pausad:
        return pausad
    vid = current_user.verkstad_id
    with get_db() as conn:
        if vid is not None:
            bilar = conn.execute("SELECT * FROM bilar WHERE verkstad_id=? ORDER BY fordonsnummer, regnr", (vid,)).fetchall()
        else:
            bilar = conn.execute("SELECT * FROM bilar ORDER BY fordonsnummer, regnr").fetchall()

    bilar_service = []
    for b in bilar:
        with get_db() as conn:
            handelser = conn.execute(
                "SELECT * FROM handelser WHERE bil_id=? ORDER BY km DESC", (b["id"],)
            ).fetchall()
        senaste_km = handelser[0]["km"] if handelser else None
        if senaste_km is None:
            continue
        panel = bygg_panel(b["id"], b["marke"], b["modell"], handelser, senaste_km, b["arsmodell"])
        atgarder = []
        for typ, info in panel.items():
            diff = info["diff"]
            iv = info["intervall"]
            if iv is None or diff is None:
                continue
            if diff >= iv:
                atgarder.append({"typ": typ, "diff": diff, "intervall": iv, "status": "warn"})
            elif diff >= iv * 0.8:
                atgarder.append({"typ": typ, "diff": diff, "intervall": iv, "status": "caution"})
        if atgarder:
            atgarder.sort(key=lambda a: (0 if a["diff"] >= a["intervall"] else 1, -(a["diff"] or 0)))
            bilar_service.append({"bil": b, "atgarder": atgarder})

    return render_template("kommande.html", bilar_service=bilar_service)

@app.route("/arbetsorder", methods=["POST"])
@login_required
def arbetsorder():
    bil_ids = request.form.getlist("bil_ids")
    if not bil_ids:
        return redirect(url_for("kommande"))

    bilar_data = []
    for bil_id in bil_ids:
        bil_id = int(bil_id)
        with get_db() as conn:
            b = conn.execute("SELECT * FROM bilar WHERE id=?", (bil_id,)).fetchone()
        if not b:
            continue
        vid = current_user.verkstad_id
        if vid is not None and b["verkstad_id"] != vid:
            continue
        with get_db() as conn:
            handelser = conn.execute(
                "SELECT * FROM handelser WHERE bil_id=? ORDER BY km DESC", (bil_id,)
            ).fetchall()
        senaste_km = handelser[0]["km"] if handelser else None
        if senaste_km is None:
            continue
        panel = bygg_panel(bil_id, b["marke"], b["modell"], handelser, senaste_km, b["arsmodell"])
        atgarder = []
        for typ, info in panel.items():
            diff = info["diff"]
            iv = info["intervall"]
            if iv is None or diff is None:
                continue
            if diff >= iv:
                status = "warn"
            elif diff >= iv * 0.8:
                status = "caution"
            else:
                continue
            atgarder.append({"typ": typ, "diff": diff, "intervall": iv, "kvar": iv - diff, "status": status})
        if atgarder:
            atgarder.sort(key=lambda a: (0 if a["status"] == "warn" else 1, a["kvar"]))
            bilar_data.append({"bil": b, "atgarder": atgarder, "senaste_km": senaste_km})

    return render_template("arbetsorder.html", bilar_data=bilar_data, today=str(date.today()))

@app.route("/fordonsbibliotek")
@login_required
def fordonsbibliotek():
    with get_db() as conn:
        modeller = conn.execute(
            "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell"
        ).fetchall()
    return render_template("fordonsbibliotek.html", modeller=modeller, nedraknare_typer=NEDRAKNARE_TYPER)

@app.route("/fordonsbibliotek/ny", methods=["GET","POST"])
@login_required
def ny_fordonsmodell():
    error = None
    if request.method == "POST":
        marke     = request.form.get("marke","").strip()
        modell    = request.form.get("modell","").strip()
        arsmodell = request.form.get("arsmodell","").strip()
        if not marke or not modell:
            error = "Märke och modell är obligatoriska."
        else:
            try:
                ar = int(arsmodell) if arsmodell.isdigit() else None
                # FIX #4 pattern: en connection för hela operationen
                with get_db() as conn:
                    cur = conn.execute(
                        "INSERT INTO fordonsmodeller (marke, modell, arsmodell) VALUES (?,?,?)",
                        (marke, modell, ar)
                    )
                    fm_id = cur.lastrowid
                    for t in NEDRAKNARE_TYPER:
                        aktiv = request.form.get(f"aktiv_{t}") == "1"
                        iv_str = request.form.get(f"iv_{t}","").strip()
                        iv_km = int(iv_str) if iv_str.isdigit() else None
                        conn.execute(
                            "INSERT OR REPLACE INTO fordonsmodell_intervall (fordonsmodell_id, service_typ, intervall_km, aktiv) VALUES (?,?,?,?)",
                            (fm_id, t, iv_km, 1 if aktiv else 0)
                        )
                    egna_namn = request.form.getlist("egen_namn")
                    egna_km   = request.form.getlist("egen_km")
                    for namn, km_str in zip(egna_namn, egna_km):
                        namn = namn.strip()
                        if namn and km_str.strip().isdigit():
                            conn.execute(
                                "INSERT OR REPLACE INTO fordonsmodell_intervall (fordonsmodell_id, service_typ, intervall_km, aktiv) VALUES (?,?,?,?)",
                                (fm_id, namn, int(km_str), 1)
                            )
                return redirect(url_for("fordonsbibliotek"))
            except Exception as e:
                error = f"Kunde inte spara: {e}"
    with get_db() as conn:
        bibliotek = conn.execute(
            "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell"
        ).fetchall()
    return render_template("ny_fordonsmodell.html", error=error,
        nedraknare_typer=NEDRAKNARE_TYPER, bibliotek=bibliotek)

@app.route("/fordonsbibliotek/<int:fm_id>/redigera", methods=["GET","POST"])
@login_required
def redigera_fordonsmodell(fm_id):
    with get_db() as conn:
        fm = conn.execute("SELECT * FROM fordonsmodeller WHERE id=?", (fm_id,)).fetchone()
        iv_rader = conn.execute(
            "SELECT service_typ, intervall_km, aktiv FROM fordonsmodell_intervall WHERE fordonsmodell_id=?", (fm_id,)
        ).fetchall()
    if not fm:
        return redirect(url_for("fordonsbibliotek"))
    intervaller = {r["service_typ"]: {"intervall": r["intervall_km"], "aktiv": bool(r["aktiv"])} for r in iv_rader}
    error = None

    if request.method == "POST":
        marke     = request.form.get("marke","").strip()
        modell    = request.form.get("modell","").strip()
        arsmodell = request.form.get("arsmodell","").strip()
        if not marke or not modell:
            error = "Märke och modell är obligatoriska."
        else:
            ar = int(arsmodell) if arsmodell.isdigit() else None
            iv_dict = {}
            # FIX #4 pattern: en connection för hela uppdateringen
            with get_db() as conn:
                conn.execute(
                    "UPDATE fordonsmodeller SET marke=?, modell=?, arsmodell=? WHERE id=?",
                    (marke, modell, ar, fm_id)
                )
                for t in NEDRAKNARE_TYPER:
                    aktiv = request.form.get(f"aktiv_{t}") == "1"
                    iv_str = request.form.get(f"iv_{t}","").strip()
                    iv_km = int(iv_str) if iv_str.isdigit() else None
                    iv_dict[t] = {"intervall": iv_km, "aktiv": aktiv}
                    conn.execute(
                        "INSERT OR REPLACE INTO fordonsmodell_intervall (fordonsmodell_id, service_typ, intervall_km, aktiv) VALUES (?,?,?,?)",
                        (fm_id, t, iv_km, 1 if aktiv else 0)
                    )
                # Ta bort gamla egna typer
                conn.execute(
                    "DELETE FROM fordonsmodell_intervall WHERE fordonsmodell_id=? AND service_typ NOT IN ({})".format(
                        ",".join("?" * len(NEDRAKNARE_TYPER))
                    ), [fm_id] + NEDRAKNARE_TYPER
                )
                egna_namn = request.form.getlist("egen_namn")
                egna_km   = request.form.getlist("egen_km")
                for namn, km_str in zip(egna_namn, egna_km):
                    namn = namn.strip()
                    if namn and km_str.strip().isdigit():
                        iv_dict[namn] = {"intervall": int(km_str), "aktiv": True}
                        conn.execute(
                            "INSERT OR REPLACE INTO fordonsmodell_intervall (fordonsmodell_id, service_typ, intervall_km, aktiv) VALUES (?,?,?,?)",
                            (fm_id, namn, int(km_str), 1)
                        )
            # Synka alla bilar av samma märke + modell + årsmodell
            with get_db() as conn:
                bilar = conn.execute(
                    "SELECT id FROM bilar WHERE marke=? AND modell=? AND (arsmodell=? OR (arsmodell IS NULL AND ? IS NULL))",
                    (marke, modell, ar, ar)
                ).fetchall()
                for b in bilar:
                    for t, info in iv_dict.items():
                        conn.execute("""
                            INSERT INTO serviceintervall (bil_id, service_typ, intervall_km, aktiv)
                            VALUES (?,?,?,?)
                            ON CONFLICT(bil_id, service_typ) DO UPDATE SET intervall_km=excluded.intervall_km, aktiv=excluded.aktiv
                        """, (b["id"], t, info["intervall"], 1 if info["aktiv"] else 0))
            return redirect(url_for("fordonsbibliotek"))
    return render_template("redigera_fordonsmodell.html", fm=fm, error=error,
        intervaller=intervaller, nedraknare_typer=NEDRAKNARE_TYPER)

@app.route("/fordonsbibliotek/<int:fm_id>/ta-bort", methods=["POST"])
@login_required
def ta_bort_fordonsmodell(fm_id):
    with get_db() as conn:
        conn.execute("DELETE FROM fordonsmodell_intervall WHERE fordonsmodell_id=?", (fm_id,))
        conn.execute("DELETE FROM fordonsmodeller WHERE id=?", (fm_id,))
    return redirect(url_for("fordonsbibliotek"))

@app.route("/importera-miltal", methods=["GET","POST"])
@login_required
def importera_miltal():
    resultat = []
    vid = current_user.verkstad_id
    if request.method == "POST":
        fil = request.files.get("csv_fil")
        if not fil or not fil.filename.endswith(".csv"):
            return render_template("importera_miltal.html", error="Välj en giltig CSV-fil.", resultat=[])

        innehall = fil.read().decode("utf-8-sig").splitlines()
        reader = csv.DictReader(innehall)
        for rad in reader:
            nycklar = {k.lower().strip(): v for k, v in rad.items()}
            regnr_raw = (nycklar.get("regnr") or nycklar.get("reg.nr") or nycklar.get("reg nr") or "").strip().upper()
            regnr = regnr_raw.replace(" ", "")
            km_str = (nycklar.get("km") or nycklar.get("miltal") or nycklar.get("kilometer") or "").strip()

            if not regnr or not km_str:
                resultat.append({"regnr": regnr or "?", "status": "fel", "msg": "Saknar regnr eller km"})
                continue
            if not km_str.isdigit():
                resultat.append({"regnr": regnr, "status": "fel", "msg": f"Ogiltigt km-värde: {km_str}"})
                continue

            km = int(km_str)
            with get_db() as conn:
                if vid is not None:
                    bil = conn.execute(
                        "SELECT * FROM bilar WHERE REPLACE(regnr,' ','')=? AND verkstad_id=?", (regnr, vid)
                    ).fetchone()
                else:
                    bil = conn.execute(
                        "SELECT * FROM bilar WHERE REPLACE(regnr,' ','')=?", (regnr,)
                    ).fetchone()

            if not bil:
                resultat.append({"regnr": regnr, "status": "fel", "msg": "Bilen finns inte i systemet"})
                continue

            with get_db() as conn:
                conn.execute(
                    "INSERT INTO handelser (bil_id, datum, km, typ, service_typer, beskrivning, skapad_av) VALUES (?,?,?,?,?,?,?)",
                    (bil["id"], str(date.today()), km, "miltal", None, None, current_user.namn)
                )
            resultat.append({"regnr": regnr, "status": "ok", "msg": f"Registrerad: {km} km"})

    return render_template("importera_miltal.html", error=None, resultat=resultat)

@app.route("/exportera")
@login_required
def exportera_data():
    import io
    vid = current_user.verkstad_id
    with get_db() as conn:
        if vid is not None:
            bilar = conn.execute("SELECT * FROM bilar WHERE verkstad_id=?", (vid,)).fetchall()
        else:
            bilar = conn.execute("SELECT * FROM bilar").fetchall()
        handelser = []
        for b in bilar:
            hs = conn.execute(
                "SELECT * FROM handelser WHERE bil_id=? ORDER BY km DESC", (b["id"],)
            ).fetchall()
            for h in hs:
                handelser.append((b, h))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["regnr", "fordonsnummer", "marke", "modell", "arsmodell", "notering",
                     "datum", "km", "typ", "service_typer", "beskrivning", "skapad_av"])
    for b, h in handelser:
        writer.writerow([
            b["regnr"], b["fordonsnummer"] or "", b["marke"], b["modell"],
            b["arsmodell"] or "", b["notering"] or "",
            h["datum"], h["km"], h["typ"],
            h["service_typer"] or "", h["beskrivning"] or "", h["skapad_av"] or ""
        ])
    if not handelser:
        for b in bilar:
            writer.writerow([
                b["regnr"], b["fordonsnummer"] or "", b["marke"], b["modell"],
                b["arsmodell"] or "", b["notering"] or "",
                "", "", "", "", "", ""
            ])

    from flask import Response
    output.seek(0)
    filename = f"revvbase_export_{date.today()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ── AUTH ──────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    ip = request.remote_addr
    blockerad, sekunder_kvar = check_rate_limit(ip)
    if blockerad:
        minuter = sekunder_kvar // 60
        sekunder = sekunder_kvar % 60
        return render_template("login.html",
            error=f"För många misslyckade försök. Försök igen om {minuter}m {sekunder}s.",
            blockerad=True)

    error = None
    if request.method == "POST":
        username = request.form.get("username","").strip().lower()
        password = request.form.get("password","")
        with get_db() as conn:
            row = conn.execute("SELECT * FROM anvandare WHERE username=?", (username,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            rensa_forsok(ip)
            slug = None
            if row["verkstad_id"]:
                with get_db() as conn2:
                    v = conn2.execute("SELECT slug FROM verkstader WHERE id=?", (row["verkstad_id"],)).fetchone()
                    slug = v["slug"] if v else None
            with get_db() as conn2:
                conn2.execute("UPDATE anvandare SET senaste_inloggning=? WHERE id=?",
                    (datetime.now().strftime("%Y-%m-%d %H:%M"), row["id"]))
            user = User(row["id"], row["username"], row["namn"], row["roll"], row["verkstad_id"], slug)
            session.permanent = True
            login_user(user, remember=False)
            next_url = request.args.get("next")
            if next_url and not next_url.startswith("/"):
                next_url = None
            if next_url:
                return redirect(next_url)
            if slug:
                return redirect(f"/{slug}")
            return redirect(url_for("index"))
        registrera_misslyckat(ip)
        _, kvar = check_rate_limit(ip)
        forsok_kvar = MAX_ATTEMPTS - len(_login_attempts[ip])
        if forsok_kvar <= 0:
            error = f"För många misslyckade försök. Kontot är låst i {kvar // 60} minuter."
        else:
            error = f"Fel användarnamn eller lösenord. {forsok_kvar} försök kvar."
    return render_template("login.html", error=error, blockerad=False)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ── ADMIN (per verkstad) ──────────────────────────────────────────────────────

PAKET_SEATS = {"bas": 1, "standard": 5, "pro": 9999}

@app.route("/admin")
@login_required
def admin():
    if current_user.roll != "admin":
        return redirect(url_for("index"))
    vid = current_user.verkstad_id
    with get_db() as conn:
        if vid is not None:
            anvandare = conn.execute(
                "SELECT id, username, namn, roll FROM anvandare WHERE verkstad_id=? ORDER BY namn", (vid,)
            ).fetchall()
            v = conn.execute("SELECT paket FROM verkstader WHERE id=?", (vid,)).fetchone()
            verkstad_paket = v["paket"] if v else "bas"
        else:
            anvandare = conn.execute("SELECT id, username, namn, roll FROM anvandare ORDER BY namn").fetchall()
            verkstad_paket = "pro"
    error = request.args.get("error")
    return render_template("admin.html", anvandare=anvandare, verkstad_paket=verkstad_paket, error=error)

@app.route("/admin/ny", methods=["POST"])
@login_required
def ny_anvandare():
    if current_user.roll != "admin":
        return redirect(url_for("index"))
    username = request.form.get("username","").strip().lower()
    namn     = request.form.get("namn","").strip()
    password = request.form.get("password","")
    roll     = request.form.get("roll","anställd")
    vid      = current_user.verkstad_id
    if not (username and namn and password):
        return redirect(url_for("admin"))
    if vid is not None:
        with get_db() as conn:
            v = conn.execute("SELECT paket FROM verkstader WHERE id=?", (vid,)).fetchone()
            paket = v["paket"] if v else "bas"
            max_seats = PAKET_SEATS.get(paket, 1)
            antal = conn.execute("SELECT COUNT(*) FROM anvandare WHERE verkstad_id=?", (vid,)).fetchone()[0]
        if antal >= max_seats:
            return redirect(url_for("admin", error=f"Paketet {paket.capitalize()} tillåter max {max_seats} användare. Uppgradera för att lägga till fler."))
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO anvandare (username, namn, password_hash, roll, verkstad_id) VALUES (?,?,?,?,?)",
                (username, namn, generate_password_hash(password), roll, vid)
            )
    except sqlite3.IntegrityError:
        return redirect(url_for("admin", error=f"E-postadressen {username} används redan."))
    return redirect(url_for("admin"))

@app.route("/admin/byt-losenord/<int:anv_id>", methods=["POST"])
@login_required
def byt_losenord(anv_id):
    if current_user.roll != "admin" and current_user.id != anv_id:
        return redirect(url_for("index"))
    password = request.form.get("password","")
    if password:
        with get_db() as conn:
            conn.execute("UPDATE anvandare SET password_hash=? WHERE id=?",
                (generate_password_hash(password), anv_id))
    return redirect(url_for("admin") if current_user.roll == "admin" else url_for("index"))

@app.route("/admin/ta-bort/<int:anv_id>", methods=["POST"])
@login_required
def ta_bort_anvandare(anv_id):
    if current_user.roll != "admin":
        return redirect(url_for("index"))
    if anv_id != current_user.id:
        with get_db() as conn:
            conn.execute("DELETE FROM anvandare WHERE id=?", (anv_id,))
    return redirect(url_for("admin"))

@app.route("/mitt-konto", methods=["GET","POST"])
@login_required
def mitt_konto():
    error = None
    success = None
    if request.method == "POST":
        gammalt = request.form.get("gammalt","")
        nytt    = request.form.get("nytt","")
        nytt2   = request.form.get("nytt2","")
        if nytt != nytt2:
            error = "De nya lösenorden matchar inte."
        elif not nytt:
            error = "Ange ett nytt lösenord."
        else:
            with get_db() as conn:
                row = conn.execute("SELECT * FROM anvandare WHERE id=?", (current_user.id,)).fetchone()
            if check_password_hash(row["password_hash"], gammalt):
                with get_db() as conn:
                    conn.execute("UPDATE anvandare SET password_hash=? WHERE id=?",
                        (generate_password_hash(nytt), current_user.id))
                success = "Lösenordet är uppdaterat!"
            else:
                error = "Fel nuvarande lösenord."
    return render_template("mitt_konto.html", error=error, success=success)

# ── SUPERADMIN ────────────────────────────────────────────────────────────────

SUPERADMIN_PASSWORD = os.environ.get("SUPERADMIN_PASSWORD", "revvbase-super-2026")

@app.route("/superadmin/login", methods=["GET","POST"])
def superadmin_login():
    ip = request.remote_addr
    blockerad, sekunder_kvar = check_rate_limit(ip, _sa_login_attempts)
    if blockerad:
        minuter = sekunder_kvar // 60
        sekunder = sekunder_kvar % 60
        return render_template("superadmin_login.html",
            error=f"För många försök. Försök igen om {minuter}m {sekunder}s.")

    error = None
    if request.method == "POST":
        pw = request.form.get("password","")
        if pw == SUPERADMIN_PASSWORD:
            rensa_forsok(ip, _sa_login_attempts)
            session["superadmin"] = True
            return redirect(url_for("superadmin"))
        registrera_misslyckat(ip, _sa_login_attempts)
        forsok_kvar = MAX_ATTEMPTS - len(_sa_login_attempts[ip])
        if forsok_kvar <= 0:
            error = "För många försök. Kontot är låst i 15 minuter."
        else:
            error = f"Fel lösenord. {forsok_kvar} försök kvar."
    return render_template("superadmin_login.html", error=error)

@app.route("/superadmin")
def superadmin():
    if not session.get("superadmin"):
        return redirect(url_for("superadmin_login"))
    with get_db() as conn:
        verkstader = conn.execute("""
            SELECT v.*,
                COUNT(DISTINCT a.id) as antal_anvandare,
                COUNT(DISTINCT b.id) as antal_bilar,
                MAX(a.senaste_inloggning) as senaste_inloggning
            FROM verkstader v
            LEFT JOIN anvandare a ON a.verkstad_id = v.id
            LEFT JOIN bilar b ON b.verkstad_id = v.id
            GROUP BY v.id
            ORDER BY v.skapad DESC
        """).fetchall()
    totalt   = len(verkstader)
    aktiva   = sum(1 for v in verkstader if v["status"] == "aktiv")
    pausade  = sum(1 for v in verkstader if v["status"] == "pausad")
    bas      = sum(1 for v in verkstader if v["paket"] == "bas")
    standard = sum(1 for v in verkstader if v["paket"] == "standard")
    pro      = sum(1 for v in verkstader if v["paket"] == "pro")
    return render_template("superadmin.html",
        verkstader=verkstader, totalt=totalt, aktiva=aktiva,
        pausade=pausade, bas=bas, standard=standard, pro=pro)

@app.route("/superadmin/ny", methods=["POST"])
def superadmin_ny_verkstad():
    if not session.get("superadmin"):
        return redirect(url_for("superadmin_login"))
    namn     = request.form.get("namn","").strip()
    slug     = request.form.get("slug","").strip().lower().replace(" ","-")
    email    = request.form.get("email","").strip().lower()
    password = request.form.get("password","").strip()
    paket    = request.form.get("paket","bas")
    if namn and slug and email and password:
        try:
            with get_db() as conn:
                cur = conn.execute(
                    "INSERT INTO verkstader (namn, slug, admin_email, paket, status, skapad) VALUES (?,?,?,?,?,?)",
                    (namn, slug, email, paket, "aktiv", str(date.today()))
                )
                verkstad_id = cur.lastrowid
                conn.execute(
                    "INSERT INTO anvandare (username, namn, password_hash, roll, verkstad_id) VALUES (?,?,?,?,?)",
                    (email, namn, generate_password_hash(password), "admin", verkstad_id)
                )
        except Exception as e:
            pass
    return redirect(url_for("superadmin"))

@app.route("/superadmin/pausa/<int:vid>", methods=["POST"])
def superadmin_pausa(vid):
    if not session.get("superadmin"):
        return redirect(url_for("superadmin_login"))
    with get_db() as conn:
        v = conn.execute("SELECT status FROM verkstader WHERE id=?", (vid,)).fetchone()
        ny_status = "pausad" if v["status"] == "aktiv" else "aktiv"
        conn.execute("UPDATE verkstader SET status=? WHERE id=?", (ny_status, vid))
    return redirect(url_for("superadmin"))

@app.route("/superadmin/ta-bort/<int:vid>", methods=["POST"])
def superadmin_ta_bort(vid):
    if not session.get("superadmin"):
        return redirect(url_for("superadmin_login"))
    with get_db() as conn:
        conn.execute("DELETE FROM anvandare WHERE verkstad_id=?", (vid,))
        conn.execute("DELETE FROM verkstader WHERE id=?", (vid,))
    return redirect(url_for("superadmin"))

@app.route("/superadmin/redigera/<int:vid>", methods=["POST"])
def superadmin_redigera(vid):
    if not session.get("superadmin"):
        return redirect(url_for("superadmin_login"))
    namn  = request.form.get("namn","").strip()
    slug  = request.form.get("slug","").strip().lower().replace(" ","-")
    email = request.form.get("email","").strip().lower()
    paket = request.form.get("paket","bas")
    if namn and slug and email:
        with get_db() as conn:
            conn.execute(
                "UPDATE verkstader SET namn=?, slug=?, admin_email=?, paket=? WHERE id=?",
                (namn, slug, email, paket, vid)
            )
    return redirect(url_for("superadmin"))

@app.route("/superadmin/logout")
def superadmin_logout():
    session.pop("superadmin", None)
    return redirect(url_for("superadmin_login"))

# ── START ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(BACKUP_DIR, exist_ok=True)
    init_db()
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM anvandare").fetchone()[0]
    if count == 0:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO anvandare (username, namn, password_hash, roll, verkstad_id) VALUES (?,?,?,?,?)",
                ("admin", "Admin", generate_password_hash("verkstad123"), "admin", None)
            )
        print("Skapade standardanvändare: admin / verkstad123")
    t = threading.Thread(target=daglig_backup, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5001, debug=False)
