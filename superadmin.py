with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_code = '''
SUPERADMIN_PASSWORD = os.environ.get("SUPERADMIN_PASSWORD", "revvbase-super-2026")

@app.route("/superadmin/login", methods=["GET","POST"])
def superadmin_login():
    error = None
    if request.method == "POST":
        pw = request.form.get("password","")
        if pw == SUPERADMIN_PASSWORD:
            session["superadmin"] = True
            return redirect(url_for("superadmin"))
        error = "Fel lösenord."
    return """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>SuperAdmin Login</title>
    <style>*{box-sizing:border-box;margin:0;padding:0}body{background:#0f1113;color:#e8eaec;font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}.box{background:#181b1e;border:1px solid #2e3338;border-radius:10px;padding:2rem;width:340px}.logo{font-size:1.8rem;font-weight:900;color:#f0a500;text-align:center;margin-bottom:1.5rem}input{width:100%;background:#22262b;border:1px solid #2e3338;border-radius:6px;color:#e8eaec;padding:.7rem;font-size:1rem;margin-bottom:1rem}button{width:100%;background:#f0a500;color:#000;border:none;border-radius:6px;padding:.75rem;font-weight:700;font-size:1rem;cursor:pointer}.err{color:#e05050;font-size:.85rem;margin-bottom:1rem}</style></head>
    <body><div class="box"><div class="logo">REVVBASE ADMIN</div>""" + (f'<div class="err">{error}</div>' if error else "") + """<form method="post"><input type="password" name="password" placeholder="Lösenord" autofocus><button>Logga in</button></form></div></body></html>"""

@app.route("/superadmin")
def superadmin():
    if not session.get("superadmin"):
        return redirect(url_for("superadmin_login"))
    with get_db() as conn:
        verkstader = conn.execute("""
            SELECT v.*,
                COUNT(DISTINCT a.id) as antal_anvandare,
                COUNT(DISTINCT b.id) as antal_bilar
            FROM verkstader v
            LEFT JOIN anvandare a ON a.verkstad_id = v.id
            LEFT JOIN bilar b ON b.verkstad_id = v.id
            GROUP BY v.id
            ORDER BY v.skapad DESC
        """).fetchall()
    totalt = len(verkstader)
    aktiva = sum(1 for v in verkstader if v["status"] == "aktiv")
    pausade = sum(1 for v in verkstader if v["status"] == "pausad")
    bas = sum(1 for v in verkstader if v["paket"] == "bas")
    standard = sum(1 for v in verkstader if v["paket"] == "standard")
    pro = sum(1 for v in verkstader if v["paket"] == "pro")
    return render_template("superadmin.html",
        verkstader=verkstader, totalt=totalt, aktiva=aktiva,
        pausade=pausade, bas=bas, standard=standard, pro=pro)

@app.route("/superadmin/ny", methods=["POST"])
def superadmin_ny_verkstad():
    if not session.get("superadmin"):
        return redirect(url_for("superadmin_login"))
    namn = request.form.get("namn","").strip()
    slug = request.form.get("slug","").strip().lower().replace(" ","-")
    email = request.form.get("email","").strip().lower()
    password = request.form.get("password","").strip()
    paket = request.form.get("paket","bas")
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

@app.route("/superadmin/logout")
def superadmin_logout():
    session.pop("superadmin", None)
    return redirect(url_for("superadmin_login"))
'''

content = content.replace("if __name__ == \"__main__\":", new_code + "\nif __name__ == \"__main__\":")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("KLART!")