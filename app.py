from flask import Flask, render_template, request, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, json, os, csv, threading, time, secrets
from datetime import date, datetime
from collections import defaultdict

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # Max 2MB upload
app.config["PERMANENT_SESSION_LIFETIME"] = 8 * 60 * 60  # 8 timmar
app.config["SESSION_COOKIE_HTTPONLY"] = True   # JS kan inte läsa session-cookie
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # CSRF-skydd
# SESSION_COOKIE_SECURE=True aktiveras automatiskt när HTTPS används

# Secret key: läs från fil eller miljövariabel för att överleva omstarter
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

DB = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "verkstad.db"))

csrf = CSRFProtect(app)
login_manager = LoginManager()

# Brute-force skydd: { ip: [timestamp, timestamp, ...] }
_login_attempts = defaultdict(list)
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minuter

def check_rate_limit(ip):
    """Returnerar (blockerad, sekunder_kvar). Rensar gamla försök."""
    nu = time.time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if nu - t < LOCKOUT_SECONDS]
    if len(_login_attempts[ip]) >= MAX_ATTEMPTS:
        kvar = int(LOCKOUT_SECONDS - (nu - _login_attempts[ip][0]))
        return True, kvar
    return False, 0

def registrera_misslyckat(ip):
    _login_attempts[ip].append(time.time())

def rensa_forsok(ip):
    _login_attempts.pop(ip, None)
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Logga in för att fortsätta."

class User(UserMixin):
    def __init__(self, id, username, namn, roll):
        self.id = id
        self.username = username
        self.namn = namn
        self.roll = roll

@login_manager.user_loader
def load_user(user_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM anvandare WHERE id=?", (user_id,)).fetchone()
    if row:
        return User(row["id"], row["username"], row["namn"], row["roll"])
    return None
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "säkerhetskopior")

SERVICE_TYPER = [
    "Oljebyte",
    "Kamrem",
    "Bromsklossar fram",
    "Bromsklossar bak",
    "Bromsskivor fram",
    "Bromsskivor bak",
    "Luftfilter",
    "Kylvätska",
    "Tändstift",
    "Drivrem",
    "Däckbyte",
    "Bromsvätska",
    "Pollenfilter",
    "Växellådsolja",
]

NEDRAKNARE_TYPER = [
    "Oljebyte", "Kamrem",
    "Bromsklossar fram", "Bromsklossar bak",
    "Bromsskivor fram", "Bromsskivor bak",
    "Luftfilter", "Kylvätska",
]

# Standardintervall i km (används som fallback när fordonsbiblioteket saknar data)
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
        # Lägg till skapad_av i handelser om saknas
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
        # Migrera miltal -> km om kolumnen heter miltal
        try:
            conn.execute("ALTER TABLE handelser RENAME COLUMN miltal TO km")
        except:
            pass
        # Migrera bilar: lägg till fordonsnummer om saknas
        try:
            conn.execute("ALTER TABLE bilar ADD COLUMN fordonsnummer TEXT")
        except:
            pass
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS kommentarer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bil_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                skapad_av TEXT,
                datum TEXT NOT NULL,
                FOREIGN KEY (bil_id) REFERENCES bilar(id)
            );
        """)

def get_fordonsmodell_intervall(marke, modell, arsmodell):
    """Hämtar intervall från fordonsbiblioteket för given märke+modell+år."""
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
    """Hämtar intervall för bil - från DB om satta, annars fordonsbibliotek, annars hårdkodad standard. Inkluderar egna servicetyper."""
    nyckel = f"{marke} {modell}"
    # Försök hämta från fordonsbibliotek först
    fm_intervall = get_fordonsmodell_intervall(marke, modell, arsmodell)
    standard = fm_intervall if fm_intervall else STANDARD_INTERVALL.get(nyckel, {})
    with get_db() as conn:
        rader = conn.execute(
            "SELECT service_typ, intervall_km, aktiv FROM serviceintervall WHERE bil_id=?", (bil_id,)
        ).fetchall()
    result = {}
    db_map = {r["service_typ"]: r for r in rader}
    # Standard nedräknare
    for t in NEDRAKNARE_TYPER:
        if t in db_map:
            r = db_map[t]
            result[t] = {"intervall": r["intervall_km"], "aktiv": bool(r["aktiv"]), "egen": False}
        elif rader:
            pass  # Inte i DB = inte satt
        elif t in standard:
            result[t] = {"intervall": standard[t], "aktiv": standard[t] is not None, "egen": False}
    # Egna servicetyper (de som inte finns i NEDRAKNARE_TYPER)
    for r in rader:
        if r["service_typ"] not in NEDRAKNARE_TYPER and bool(r["aktiv"]):
            result[r["service_typ"]] = {"intervall": r["intervall_km"], "aktiv": True, "egen": True}
    return result

def spara_intervall(bil_id, intervall_dict):
    with get_db() as conn:
        # Ta bort egna typer som inte längre finns med
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
            # Aldrig loggat — anta gjort vid 0 km (fabriksny)
            diff = senaste_km if senaste_km is not None else None
            aldrig_gjort = True
        panel[t] = {"diff": diff, "intervall": iv, "aldrig_gjort": aldrig_gjort}
    return panel

def daglig_backup():
    while True:
        nu = datetime.now()
        # Kör backup en gång per dag
        idag = nu.strftime("%Y-%m-%d")
        os.makedirs(BACKUP_DIR, exist_ok=True)
        fil = os.path.join(BACKUP_DIR, f"{idag}.csv")
        if not os.path.exists(fil):
            try:
                with get_db() as conn:
                    bilar = conn.execute("SELECT * FROM bilar").fetchall()
                    handelser = conn.execute(
                        "SELECT h.*, b.regnr, b.fordonsnummer, b.marke, b.modell FROM handelser h JOIN bilar b ON h.bil_id=b.id"
                    ).fetchall()
                with open(fil, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["typ","id","bil_id","regnr","fordonsnummer","marke","modell","datum","km","handelse_typ","service_typer","beskrivning"])
                    for h in handelser:
                        writer.writerow([
                            "händelse", h["id"], h["bil_id"],
                            h["regnr"], h["fordonsnummer"], h["marke"], h["modell"],
                            h["datum"], h["km"], h["typ"],
                            h["service_typer"], h["beskrivning"]
                        ])
            except Exception as e:
                print(f"Backup fel: {e}")
        # Vänta 1 timme och kolla igen
        time.sleep(3600)


@app.route('/')
def landing():
    return open('landing.html', encoding='utf-8').read()

# ── ROUTES ──────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    with get_db() as conn:
        if q:
            bilar = conn.execute(
                "SELECT * FROM bilar WHERE regnr LIKE ? OR marke LIKE ? OR modell LIKE ? OR fordonsnummer LIKE ? OR notering LIKE ? ORDER BY regnr",
                (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%")
            ).fetchall()
        else:
            bilar = conn.execute("SELECT * FROM bilar ORDER BY fordonsnummer, regnr").fetchall()
    return render_template("index.html", bilar=bilar, q=q)

@app.route("/bil/ny", methods=["GET","POST"])
@login_required
def ny_bil():
    error = None
    with get_db() as conn:
        bibliotek = conn.execute(
            "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell"
        ).fetchall()

    if request.method == "POST":
        regnr        = request.form.get("regnr","").strip().upper()
        fordonsnummer= request.form.get("fordonsnummer","").strip()
        marke        = request.form.get("marke","").strip()
        modell       = request.form.get("modell","").strip()
        arsmodell    = request.form.get("arsmodell","").strip()
        notering     = request.form.get("notering","").strip()

        if not regnr or not marke or not modell:
            error = "Reg.nr, märke och modell är obligatoriska."
        else:
            try:
                with get_db() as conn:
                    cur = conn.execute(
                        "INSERT INTO bilar (regnr,fordonsnummer,marke,modell,arsmodell,notering) VALUES (?,?,?,?,?,?)",
                        (regnr, fordonsnummer or None, marke, modell, arsmodell or None, notering)
                    )
                    bil_id = cur.lastrowid

                # Spara intervall
                iv_dict = {}
                for t in NEDRAKNARE_TYPER:
                    aktiv = request.form.get(f"aktiv_{t}") == "1"
                    iv_str = request.form.get(f"iv_{t}", "").strip()
                    iv_km = int(iv_str) if iv_str.isdigit() else None
                    iv_dict[t] = {"intervall": iv_km, "aktiv": aktiv, "egen": False}
                # Egna servicetyper
                egna_namn = request.form.getlist("egen_namn")
                egna_km   = request.form.getlist("egen_km")
                for namn, km_str in zip(egna_namn, egna_km):
                    namn = namn.strip()
                    if namn and km_str.strip().isdigit():
                        iv_dict[namn] = {"intervall": int(km_str), "aktiv": True, "egen": True}
                spara_intervall(bil_id, iv_dict)

                # Skapa fordonsprofil i biblioteket om den inte finns
                ar = int(arsmodell) if arsmodell.isdigit() else None
                with get_db() as conn:
                    befintlig = conn.execute(
                        "SELECT id FROM fordonsmodeller WHERE marke=? AND modell=? AND (arsmodell=? OR (arsmodell IS NULL AND ? IS NULL))",
                        (marke, modell, ar, ar)
                    ).fetchone()
                if not befintlig:
                    with get_db() as conn:
                        cur = conn.execute(
                            "INSERT INTO fordonsmodeller (marke, modell, arsmodell) VALUES (?,?,?)",
                            (marke, modell, ar)
                        )
                        fm_id = cur.lastrowid
                    for t, info in iv_dict.items():
                        with get_db() as conn:
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
    filter_typ = request.args.get("filter", "").strip()
    with get_db() as conn:
        b = conn.execute("SELECT * FROM bilar WHERE id=?", (bil_id,)).fetchone()
        if not b:
            return redirect(url_for("index"))
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

    senaste_km = alla_handelser[0]["km"] if alla_handelser else None
    panel = bygg_panel(bil_id, b["marke"], b["modell"], alla_handelser, senaste_km)

    with get_db() as conn:
        kommentarer = conn.execute(
            "SELECT * FROM kommentarer WHERE bil_id=? ORDER BY id DESC", (bil_id,)
        ).fetchall()

    return render_template("bil.html", bil=b, handelser=handelser,
        panel=panel, senaste_km=senaste_km,
        service_typer=SERVICE_TYPER, filter_typ=filter_typ,
        kommentarer=kommentarer)

@app.route("/bil/<int:bil_id>/redigera", methods=["GET","POST"])
@login_required
def redigera_bil(bil_id):
    with get_db() as conn:
        b = conn.execute("SELECT * FROM bilar WHERE id=?", (bil_id,)).fetchone()
    intervaller = get_intervall(bil_id, b["marke"], b["modell"])
    error = None
    if request.method == "POST":
        marke        = request.form.get("marke","").strip()
        modell       = request.form.get("modell","").strip()
        fordonsnummer= request.form.get("fordonsnummer","").strip()
        arsmodell    = request.form.get("arsmodell","").strip()
        notering     = request.form.get("notering","").strip()
        if not marke or not modell:
            error = "Märke och modell är obligatoriska."
        else:
            with get_db() as conn:
                conn.execute(
                    "UPDATE bilar SET marke=?,modell=?,fordonsnummer=?,arsmodell=?,notering=? WHERE id=?",
                    (marke, modell, fordonsnummer or None, arsmodell or None, notering, bil_id)
                )
            # Uppdatera intervall
            iv_dict = {}
            for t in NEDRAKNARE_TYPER:
                aktiv = request.form.get(f"aktiv_{t}") == "1"
                iv_str = request.form.get(f"iv_{t}", "").strip()
                iv_km = int(iv_str) if iv_str.isdigit() else None
                iv_dict[t] = {"intervall": iv_km, "aktiv": aktiv, "egen": False}
            # Egna servicetyper
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
    with get_db() as conn:
        b = conn.execute("SELECT * FROM bilar WHERE id=?", (bil_id,)).fetchone()
    if not b:
        return redirect(url_for("index"))
    # Bygg komplett lista med servicetyper inkl. egna
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
                # Spara direkt utan steg 3
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
    with get_db() as conn:
        b = conn.execute("SELECT * FROM bilar WHERE id=?", (bil_id,)).fetchone()
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
    with get_db() as conn:
        conn.execute("DELETE FROM kommentarer WHERE id=? AND bil_id=?", (k_id, bil_id))
    return redirect(url_for("bil", bil_id=bil_id))

@app.route("/bil/<int:bil_id>/ta-bort-handelse/<int:h_id>", methods=["POST"])
@login_required
def ta_bort_handelse(bil_id, h_id):
    with get_db() as conn:
        conn.execute("DELETE FROM handelser WHERE id=? AND bil_id=?", (h_id, bil_id))
    return redirect(url_for("bil", bil_id=bil_id))

@app.route("/bil/<int:bil_id>/ta-bort", methods=["POST"])
@login_required
def ta_bort_bil(bil_id):
    with get_db() as conn:
        conn.execute("DELETE FROM handelser WHERE bil_id=?", (bil_id,))
        conn.execute("DELETE FROM serviceintervall WHERE bil_id=?", (bil_id,))
        conn.execute("DELETE FROM bilar WHERE id=?", (bil_id,))
    return redirect(url_for("index"))

@app.route("/bil/<int:bil_id>/print")
@login_required
def print_bil(bil_id):
    with get_db() as conn:
        b = conn.execute("SELECT * FROM bilar WHERE id=?", (bil_id,)).fetchone()
        handelser = conn.execute(
            "SELECT * FROM handelser WHERE bil_id=? ORDER BY km DESC", (bil_id,)
        ).fetchall()
    return render_template("print_bil.html", bil=b, handelser=handelser, today=str(date.today()))


@app.route("/kommande")
@login_required
def kommande():
    with get_db() as conn:
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
            if iv is None:
                continue
            # Visa om försenad ELLER inom 20% av intervallet
            if diff is None:
                pass  # Ingen km loggad alls, hoppa över
            elif diff >= iv:
                atgarder.append({"typ": typ, "diff": diff, "intervall": iv, "status": "warn"})
            elif diff >= iv * 0.8:
                atgarder.append({"typ": typ, "diff": diff, "intervall": iv, "status": "caution"})
        if atgarder:
            # Sortera: försenade först, sedan närmast
            atgarder.sort(key=lambda a: (
                0 if a["diff"] is None or a["diff"] >= a["intervall"] else 1,
                -(a["diff"] or 0)
            ))
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
            handelser = conn.execute(
                "SELECT * FROM handelser WHERE bil_id=? ORDER BY km DESC", (bil_id,)
            ).fetchall()
        if not b:
            continue
        senaste_km = handelser[0]["km"] if handelser else None
        if senaste_km is None:
            continue
        panel = bygg_panel(bil_id, b["marke"], b["modell"], handelser, senaste_km, b["arsmodell"])
        atgarder = []
        for typ, info in panel.items():
            diff = info["diff"]
            iv = info["intervall"]
            if iv is None:
                continue
            if diff is None:
                continue
            if diff >= iv:
                status = "warn"
            elif diff >= iv * 0.8:
                status = "caution"
            else:
                continue
            kvar = iv - diff
            atgarder.append({
                "typ": typ,
                "diff": diff,
                "intervall": iv,
                "kvar": kvar,
                "status": status
            })
        if atgarder:
            atgarder.sort(key=lambda a: (0 if a["status"] == "warn" else 1, a["kvar"]))
            bilar_data.append({"bil": b, "atgarder": atgarder, "senaste_km": senaste_km})

    today = str(date.today())
    return render_template("arbetsorder.html", bilar_data=bilar_data, today=today)


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
        marke   = request.form.get("marke","").strip()
        modell  = request.form.get("modell","").strip()
        arsmodell = request.form.get("arsmodell","").strip()
        if not marke or not modell:
            error = "Märke och modell är obligatoriska."
        else:
            try:
                with get_db() as conn:
                    cur = conn.execute(
                        "INSERT INTO fordonsmodeller (marke, modell, arsmodell) VALUES (?,?,?)",
                        (marke, modell, int(arsmodell) if arsmodell.isdigit() else None)
                    )
                    fm_id = cur.lastrowid
                # Spara intervall
                for t in NEDRAKNARE_TYPER:
                    aktiv = request.form.get(f"aktiv_{t}") == "1"
                    iv_str = request.form.get(f"iv_{t}","").strip()
                    iv_km = int(iv_str) if iv_str.isdigit() else None
                    with get_db() as conn:
                        conn.execute(
                            "INSERT OR REPLACE INTO fordonsmodell_intervall (fordonsmodell_id, service_typ, intervall_km, aktiv) VALUES (?,?,?,?)",
                            (fm_id, t, iv_km, 1 if aktiv else 0)
                        )
                # Egna servicetyper
                egna_namn = request.form.getlist("egen_namn")
                egna_km   = request.form.getlist("egen_km")
                for namn, km_str in zip(egna_namn, egna_km):
                    namn = namn.strip()
                    if namn and km_str.strip().isdigit():
                        with get_db() as conn:
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
        marke   = request.form.get("marke","").strip()
        modell  = request.form.get("modell","").strip()
        arsmodell = request.form.get("arsmodell","").strip()
        if not marke or not modell:
            error = "Märke och modell är obligatoriska."
        else:
            with get_db() as conn:
                conn.execute(
                    "UPDATE fordonsmodeller SET marke=?, modell=?, arsmodell=? WHERE id=?",
                    (marke, modell, int(arsmodell) if arsmodell.isdigit() else None, fm_id)
                )
            iv_dict = {}
            for t in NEDRAKNARE_TYPER:
                aktiv = request.form.get(f"aktiv_{t}") == "1"
                iv_str = request.form.get(f"iv_{t}","").strip()
                iv_km = int(iv_str) if iv_str.isdigit() else None
                iv_dict[t] = {"intervall": iv_km, "aktiv": aktiv}
                with get_db() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO fordonsmodell_intervall (fordonsmodell_id, service_typ, intervall_km, aktiv) VALUES (?,?,?,?)",
                        (fm_id, t, iv_km, 1 if aktiv else 0)
                    )
            # Egna servicetyper
            egna_namn = request.form.getlist("egen_namn")
            egna_km   = request.form.getlist("egen_km")
            # Ta bort gamla egna typer från fordonsmodell_intervall
            with get_db() as conn:
                conn.execute(
                    "DELETE FROM fordonsmodell_intervall WHERE fordonsmodell_id=? AND service_typ NOT IN ({})".format(
                        ",".join("?" * len(NEDRAKNARE_TYPER))
                    ), [fm_id] + NEDRAKNARE_TYPER
                )
            for namn, km_str in zip(egna_namn, egna_km):
                namn = namn.strip()
                if namn and km_str.strip().isdigit():
                    iv_dict[namn] = {"intervall": int(km_str), "aktiv": True}
                    with get_db() as conn:
                        conn.execute(
                            "INSERT OR REPLACE INTO fordonsmodell_intervall (fordonsmodell_id, service_typ, intervall_km, aktiv) VALUES (?,?,?,?)",
                            (fm_id, namn, int(km_str), 1)
                        )
            # Synka alla bilar av samma märke + modell + årsmodell
            ar = int(arsmodell) if arsmodell.isdigit() else None
            with get_db() as conn:
                bilar = conn.execute(
                    "SELECT id FROM bilar WHERE marke=? AND modell=? AND (arsmodell=? OR (arsmodell IS NULL AND ? IS NULL))",
                    (marke, modell, ar, ar)
                ).fetchall()
            for b in bilar:
                for t, info in iv_dict.items():
                    with get_db() as conn:
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
    if request.method == "POST":
        fil = request.files.get("csv_fil")
        if not fil or not fil.filename.endswith(".csv"):
            return render_template("importera_miltal.html", error="Välj en giltig CSV-fil.", resultat=[])

        innehall = fil.read().decode("utf-8-sig").splitlines()
        reader = csv.DictReader(innehall)

        # Normalisera kolumnnamn (hantera olika stavningar)
        for rad in reader:
            nycklar = {k.lower().strip(): v for k, v in rad.items()}
            regnr_raw = (nycklar.get("regnr") or nycklar.get("reg.nr") or nycklar.get("reg nr") or "").strip().upper()
            regnr = regnr_raw.replace(" ", "")  # Normalisera bort mellanslag för jämförelse
            km_str = (nycklar.get("km") or nycklar.get("miltal") or nycklar.get("kilometer") or "").strip()

            if not regnr or not km_str:
                resultat.append({"regnr": regnr or "?", "status": "fel", "msg": "Saknar regnr eller km"})
                continue

            if not km_str.isdigit():
                resultat.append({"regnr": regnr, "status": "fel", "msg": f"Ogiltigt km-värde: {km_str}"})
                continue

            km = int(km_str)
            with get_db() as conn:
                bil = conn.execute("SELECT * FROM bilar WHERE REPLACE(regnr,' ','')=?", (regnr,)).fetchone()

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


@app.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    ip = request.remote_addr
    blockerad, sekunder_kvar = check_rate_limit(ip)
    if blockerad:
        minuter = sekunder_kvar // 60
        sekunder = sekunder_kvar % 60
        error = f"För många misslyckade försök. Försök igen om {minuter}m {sekunder}s."
        return render_template("login.html", error=error, blockerad=True)

    error = None
    if request.method == "POST":
        username = request.form.get("username","").strip().lower()
        password = request.form.get("password","")
        with get_db() as conn:
            row = conn.execute("SELECT * FROM anvandare WHERE username=?", (username,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            rensa_forsok(ip)
            user = User(row["id"], row["username"], row["namn"], row["roll"])
            session.permanent = True
            login_user(user, remember=False)
            next_url = request.args.get("next")
            if next_url and not next_url.startswith("/"):
                next_url = None
            return redirect(next_url or url_for("index"))
        registrera_misslyckat(ip)
        _, kvar = check_rate_limit(ip)
        forsok_kvar = MAX_ATTEMPTS - len(_login_attempts[ip])
        if forsok_kvar <= 0:
            minuter = kvar // 60
            error = f"För många misslyckade försök. Kontot är låst i {minuter} minuter."
        else:
            error = f"Fel användarnamn eller lösenord. {forsok_kvar} försök kvar."
    return render_template("login.html", error=error, blockerad=False)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/admin")
@login_required
def admin():
    if current_user.roll != "admin":
        return redirect(url_for("index"))
    with get_db() as conn:
        anvandare = conn.execute("SELECT id, username, namn, roll FROM anvandare ORDER BY namn").fetchall()
    return render_template("admin.html", anvandare=anvandare)

@app.route("/admin/ny", methods=["POST"])
@login_required
def ny_anvandare():
    if current_user.roll != "admin":
        return redirect(url_for("index"))
    username = request.form.get("username","").strip().lower()
    namn     = request.form.get("namn","").strip()
    password = request.form.get("password","")
    roll     = request.form.get("roll","anställd")
    if username and namn and password:
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO anvandare (username, namn, password_hash, roll) VALUES (?,?,?,?)",
                    (username, namn, generate_password_hash(password), roll)
                )
        except: pass
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

if __name__ == "__main__":
    os.makedirs(BACKUP_DIR, exist_ok=True)
    init_db()
    # Skapa standard-admin om inga användare finns
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM anvandare").fetchone()[0]
    if count == 0:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO anvandare (username, namn, password_hash, roll) VALUES (?,?,?,?)",
                ("admin", "Admin", generate_password_hash("verkstad123"), "admin")
            )
        print("Skapade standardanvändare: admin / verkstad123")
        print("Byt lösenord direkt efter inloggning!")
    t = threading.Thread(target=daglig_backup, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5001, debug=False)
