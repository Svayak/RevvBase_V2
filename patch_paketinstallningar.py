# Kör från ~/RevvBase_V2:
# python3 patch_paketinstallningar.py

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. Lägg till paketinstallningar-tabell i init_db ──────────────────────────
old_init = """        try:
            conn.execute("ALTER TABLE anvandare ADD COLUMN senaste_inloggning TEXT")
        except: pass
        # Migration: byt UNIQUE(regnr) mot UNIQUE(regnr, verkstad_id)"""

new_init = """        try:
            conn.execute("ALTER TABLE anvandare ADD COLUMN senaste_inloggning TEXT")
        except: pass
        # Paketinställningar
        conn.executescript(\"\"\"
            CREATE TABLE IF NOT EXISTS paketinstallningar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paket TEXT NOT NULL UNIQUE,
                max_anvandare INTEGER NOT NULL DEFAULT 1,
                max_bilar INTEGER NOT NULL DEFAULT 5,
                obegransad_anvandare INTEGER NOT NULL DEFAULT 0,
                obegransad_bilar INTEGER NOT NULL DEFAULT 0,
                pris INTEGER NOT NULL DEFAULT 0
            );
        \"\"\")
        # Seed standardvärden om tabellen är tom
        befintliga = conn.execute("SELECT COUNT(*) FROM paketinstallningar").fetchone()[0]
        if befintliga == 0:
            conn.executemany(
                "INSERT INTO paketinstallningar (paket, max_anvandare, max_bilar, obegransad_anvandare, obegransad_bilar, pris) VALUES (?,?,?,?,?,?)",
                [
                    ("bas",      1,  5,  0, 0, 299),
                    ("standard", 5,  20, 0, 0, 599),
                    ("pro",      10, 100, 0, 0, 999),
                ]
            )
        # Migration: byt UNIQUE(regnr) mot UNIQUE(regnr, verkstad_id)"""

# ── 2. Lägg till hjälpfunktion get_paket_limits ───────────────────────────────
old_get_db = """def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn"""

new_get_db = """def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_paket_limits(paket):
    \"\"\"Hämtar max_anvandare och max_bilar för ett paket från databasen.\"\"\"
    with get_db() as conn:
        row = conn.execute("SELECT * FROM paketinstallningar WHERE paket=?", (paket,)).fetchone()
    if not row:
        return {"max_anvandare": 1, "max_bilar": 5, "pris": 0}
    return {
        "max_anvandare": 999999 if row["obegransad_anvandare"] else row["max_anvandare"],
        "max_bilar":     999999 if row["obegransad_bilar"]     else row["max_bilar"],
        "pris":          row["pris"],
    }"""

# ── 3. Ersätt hårdkodad PAKET_FORDON i ny_bil ────────────────────────────────
old_paket_fordon = """            # Kontrollera fordonskvot
            if current_user.verkstad_id is not None:
                PAKET_FORDON = {"bas": 25, "standard": 100, "pro": 9999}
                with get_db() as conn:
                    v = conn.execute("SELECT paket FROM verkstader WHERE id=?", (current_user.verkstad_id,)).fetchone()
                    paket = v["paket"] if v else "bas"
                    antal = conn.execute("SELECT COUNT(*) FROM bilar WHERE verkstad_id=?", (current_user.verkstad_id,)).fetchone()[0]
                max_fordon = PAKET_FORDON.get(paket, 25)
                if antal >= max_fordon:
                    error = f"Paketet {paket.capitalize()} tillåter max {max_fordon} fordon. Uppgradera för att lägga till fler." """

new_paket_fordon = """            # Kontrollera fordonskvot
            if current_user.verkstad_id is not None:
                with get_db() as conn:
                    v = conn.execute("SELECT paket FROM verkstader WHERE id=?", (current_user.verkstad_id,)).fetchone()
                    paket = v["paket"] if v else "bas"
                    antal = conn.execute("SELECT COUNT(*) FROM bilar WHERE verkstad_id=?", (current_user.verkstad_id,)).fetchone()[0]
                limits = get_paket_limits(paket)
                max_fordon = limits["max_bilar"]
                if antal >= max_fordon:
                    error = f"Paketet {paket.capitalize()} tillåter max {max_fordon} fordon. Uppgradera för att lägga till fler." """

# ── 4. Ersätt hårdkodad PAKET_SEATS i ny_anvandare ───────────────────────────
old_paket_seats = """    if vid is not None:
        with get_db() as conn:
            v = conn.execute("SELECT paket FROM verkstader WHERE id=?", (vid,)).fetchone()
            paket = v["paket"] if v else "bas"
            max_seats = PAKET_SEATS.get(paket, 1)
            antal = conn.execute("SELECT COUNT(*) FROM anvandare WHERE verkstad_id=?", (vid,)).fetchone()[0]
        if antal >= max_seats:
            return redirect(url_for("admin", error=f"Paketet {paket.capitalize()} tillåter max {max_seats} användare. Uppgradera för att lägga till fler."))"""

new_paket_seats = """    if vid is not None:
        with get_db() as conn:
            v = conn.execute("SELECT paket FROM verkstader WHERE id=?", (vid,)).fetchone()
            paket = v["paket"] if v else "bas"
            antal = conn.execute("SELECT COUNT(*) FROM anvandare WHERE verkstad_id=?", (vid,)).fetchone()[0]
        limits = get_paket_limits(paket)
        max_seats = limits["max_anvandare"]
        if antal >= max_seats:
            return redirect(url_for("admin", error=f"Paketet {paket.capitalize()} tillåter max {max_seats} användare. Uppgradera för att lägga till fler."))"""

# ── 5. Ersätt hårdkodad admin-visning ────────────────────────────────────────
old_admin_paket = """    error = request.args.get("error")
    return render_template("admin.html", anvandare=anvandare, verkstad_paket=verkstad_paket, error=error)"""

new_admin_paket = """    error = request.args.get("error")
    limits = get_paket_limits(verkstad_paket)
    return render_template("admin.html", anvandare=anvandare, verkstad_paket=verkstad_paket, error=error, limits=limits)"""

# ── 6. Lägg till superadmin paketinställningar-route ─────────────────────────
old_superadmin_logout = """@app.route("/superadmin/logout")
def superadmin_logout():
    session.pop("superadmin", None)
    return redirect(url_for("superadmin_login"))"""

new_superadmin_logout = """@app.route("/superadmin/paket", methods=["GET","POST"])
def superadmin_paket():
    if not session.get("superadmin"):
        return redirect(url_for("superadmin_login"))
    if request.method == "POST":
        for paket in ["bas", "standard", "pro"]:
            max_anv  = request.form.get(f"{paket}_max_anvandare", "1").strip()
            max_bil  = request.form.get(f"{paket}_max_bilar", "5").strip()
            obeg_anv = 1 if request.form.get(f"{paket}_obegransad_anvandare") else 0
            obeg_bil = 1 if request.form.get(f"{paket}_obegransad_bilar") else 0
            pris     = request.form.get(f"{paket}_pris", "0").strip()
            max_anv  = int(max_anv)  if max_anv.isdigit()  else 1
            max_bil  = int(max_bil)  if max_bil.isdigit()  else 5
            pris     = int(pris)     if pris.isdigit()     else 0
            with get_db() as conn:
                conn.execute(\"\"\"
                    INSERT INTO paketinstallningar (paket, max_anvandare, max_bilar, obegransad_anvandare, obegransad_bilar, pris)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(paket) DO UPDATE SET
                        max_anvandare=excluded.max_anvandare,
                        max_bilar=excluded.max_bilar,
                        obegransad_anvandare=excluded.obegransad_anvandare,
                        obegransad_bilar=excluded.obegransad_bilar,
                        pris=excluded.pris
                \"\"\", (paket, max_anv, max_bil, obeg_anv, obeg_bil, pris))
        return redirect(url_for("superadmin", msg="✓ Paketinställningar sparade!"))
    with get_db() as conn:
        paket_rader = conn.execute("SELECT * FROM paketinstallningar ORDER BY id").fetchall()
    paket_dict = {r["paket"]: r for r in paket_rader}
    return render_template("superadmin_paket.html", paket=paket_dict)

@app.route("/superadmin/logout")
def superadmin_logout():
    session.pop("superadmin", None)
    return redirect(url_for("superadmin_login"))"""

# ── Applicera alla ändringar ──────────────────────────────────────────────────
errors = []
if old_init not in content:           errors.append("init_db seed")
if old_get_db not in content:         errors.append("get_db / get_paket_limits")
if old_paket_fordon not in content:   errors.append("PAKET_FORDON i ny_bil")
if old_paket_seats not in content:    errors.append("PAKET_SEATS i ny_anvandare")
if old_admin_paket not in content:    errors.append("admin limits")
if old_superadmin_logout not in content: errors.append("superadmin_logout")

if errors:
    print("FEL: Hittade inte följande strängar i app.py:")
    for e in errors:
        print(f"  - {e}")
    print("Kontrollera att app.py är uppdaterad.")
else:
    content = content.replace(old_init, new_init)
    content = content.replace(old_get_db, new_get_db)
    content = content.replace(old_paket_fordon, new_paket_fordon)
    content = content.replace(old_paket_seats, new_paket_seats)
    content = content.replace(old_admin_paket, new_admin_paket)
    content = content.replace(old_superadmin_logout, new_superadmin_logout)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ app.py uppdaterad!")

