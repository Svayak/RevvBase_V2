import shutil, py_compile, os

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

shutil.copy('app.py', 'app.py.bak')
print("Backup: app.py.bak")

changes = 0

# ── 1. ny_bil: filtrera bibliotek på verkstad_id ──────────────────────────────
old = '''        bibliotek = conn.execute(
            "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell"
        ).fetchall()'''
new = '''        vid = current_user.verkstad_id
        if vid is not None:
            bibliotek = conn.execute(
                "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id WHERE f.verkstad_id=? GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell",
                (vid,)
            ).fetchall()
        else:
            bibliotek = conn.execute(
                "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell"
            ).fetchall()'''
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print("✓ 1. ny_bil bibliotek-query scopad")
else:
    print("✗ 1. ny_bil bibliotek-query — HITTADES INTE")

# ── 2. fordonsbibliotek: filtrera på verkstad_id ──────────────────────────────
old = '''@app.route("/fordonsbibliotek")
@login_required
def fordonsbibliotek():
    with get_db() as conn:
        modeller = conn.execute(
            "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell"
        ).fetchall()
    return render_template("fordonsbibliotek.html", modeller=modeller, nedraknare_typer=NEDRAKNARE_TYPER)'''
new = '''@app.route("/fordonsbibliotek")
@login_required
def fordonsbibliotek():
    vid = current_user.verkstad_id
    with get_db() as conn:
        if vid is not None:
            modeller = conn.execute(
                "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id WHERE f.verkstad_id=? GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell",
                (vid,)
            ).fetchall()
        else:
            modeller = conn.execute(
                "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell"
            ).fetchall()
    return render_template("fordonsbibliotek.html", modeller=modeller, nedraknare_typer=NEDRAKNARE_TYPER)'''
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print("✓ 2. fordonsbibliotek-route scopad")
else:
    print("✗ 2. fordonsbibliotek-route — HITTADES INTE")

# ── 3. ny_fordonsmodell: filtrera bibliotek-kopiera på verkstad_id ────────────
old = '''    with get_db() as conn:
        bibliotek = conn.execute(
            "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell"
        ).fetchall()
    return render_template("ny_fordonsmodell.html", error=error,
        nedraknare_typer=NEDRAKNARE_TYPER, bibliotek=bibliotek)'''
new = '''    vid2 = current_user.verkstad_id
    with get_db() as conn:
        if vid2 is not None:
            bibliotek = conn.execute(
                "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id WHERE f.verkstad_id=? GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell",
                (vid2,)
            ).fetchall()
        else:
            bibliotek = conn.execute(
                "SELECT f.*, GROUP_CONCAT(fi.service_typ || ':' || COALESCE(fi.intervall_km,'') || ':' || fi.aktiv, '|') as intervall_str FROM fordonsmodeller f LEFT JOIN fordonsmodell_intervall fi ON fi.fordonsmodell_id=f.id GROUP BY f.id ORDER BY f.marke, f.modell, f.arsmodell"
            ).fetchall()
    return render_template("ny_fordonsmodell.html", error=error,
        nedraknare_typer=NEDRAKNARE_TYPER, bibliotek=bibliotek)'''
if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print("✓ 3. ny_fordonsmodell bibliotek-query scopad")
else:
    print("✗ 3. ny_fordonsmodell bibliotek-query — HITTADES INTE")

# ── Skriv och validera ────────────────────────────────────────────────────────
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

try:
    py_compile.compile('app.py', doraise=True)
    print(f"\n✓ Syntax OK — {changes}/3 ändringar applicerade")
    print("\nKör nu:")
    print("  git add . && git commit -m 'Scopa fordonsbibliotek per verkstad' && git push")
except py_compile.PyCompileError as e:
    print(f"\n✗ SYNTAXFEL: {e}")
    shutil.copy('app.py.bak', 'app.py')
    print("Återställde app.py från backup")
