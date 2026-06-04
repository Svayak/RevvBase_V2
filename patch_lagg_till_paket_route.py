# Kör från ~/RevvBase_V2:
# python3 patch_lagg_till_paket_route.py

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

ny_route = """
@app.route("/superadmin/paket", methods=["GET","POST"])
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
            max_anv  = int(max_anv) if max_anv.isdigit() else 1
            max_bil  = int(max_bil) if max_bil.isdigit() else 5
            pris     = int(pris)    if pris.isdigit()    else 0
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

"""

anchor = """@app.route("/superadmin/logout")
def superadmin_logout():"""

if anchor not in content:
    print("FEL: Hittade inte superadmin_logout-routen")
elif "superadmin_paket" in content:
    print("INFO: superadmin_paket-routen finns redan i app.py")
else:
    content = content.replace(anchor, ny_route + anchor)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ KLART! Route tillagd.")
