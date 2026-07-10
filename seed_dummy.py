"""Lägger in dummy-data för lokal test:
- 10 bilar med milställning och serviceposter
- 4 fordonsmodeller i fordonsbiblioteket med serviceintervall

Körs mot samma databas som appen (DB_PATH, standard verkstad.db):

    python seed_dummy.py

Idempotent: hoppar över bilar (regnr) och modeller (märke+modell) som redan finns.
"""
import os
import sqlite3
import json
import random
from datetime import date, timedelta

DB = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "verkstad.db"))

# Modeller som finns i STANDARD_INTERVALL → serviceintervall räknas ut automatiskt
BILAR = [
    ("ABC123", "101", "Ford",    "Transit", 2021),
    ("DEF456", "102", "Ford",    "Transit", 2019),
    ("GHI789", "103", "Renault", "Master",  2022),
    ("JKL012", "104", "Renault", "Master",  2020),
    ("MNO345", "105", "Opel",    "Movano",  2023),
    ("PQR678", "106", "Opel",    "Movano",  2018),
    ("STU901", "107", "Renault", "Scénic",  2021),
    ("VWX234", "108", "Renault", "Scénic",  2017),
    ("YZA567", "109", "Ford",    "Transit", 2024),
    ("BCD890", "110", "Renault", "Master",  2016),
]

SERVICE_TYPER = ["Oljebyte", "Bromsklossar fram", "Luftfilter"]

# Fordonsmodeller till fordonsbiblioteket, med serviceintervall (km).
# Matchar STANDARD_INTERVALL i app.py. None = inget intervall (inaktivt).
MODELLER = {
    ("Ford", "Transit"): {
        "Oljebyte": 15000, "Kamrem": 100000,
        "Bromsklossar fram": 30000, "Bromsklossar bak": 40000,
        "Bromsskivor fram": 60000, "Bromsskivor bak": 80000,
        "Luftfilter": 30000, "Kylvätska": 100000,
    },
    ("Renault", "Master"): {
        "Oljebyte": 18000, "Kamrem": 100000,
        "Bromsklossar fram": 30000, "Bromsklossar bak": 40000,
        "Bromsskivor fram": 60000, "Bromsskivor bak": 80000,
        "Luftfilter": 30000, "Kylvätska": 100000,
    },
    ("Opel", "Movano"): {
        "Oljebyte": 25000, "Kamrem": None,
        "Bromsklossar fram": 30000, "Bromsklossar bak": 40000,
        "Bromsskivor fram": 60000, "Bromsskivor bak": 80000,
        "Luftfilter": 30000, "Kylvätska": 100000,
    },
    ("Renault", "Scénic"): {
        "Oljebyte": 18000, "Kamrem": 100000,
        "Bromsklossar fram": 30000, "Bromsklossar bak": 40000,
        "Bromsskivor fram": 60000, "Bromsskivor bak": 80000,
        "Luftfilter": 30000, "Kylvätska": 100000,
    },
}


def seed_fordonsbibliotek(conn, verkstad_id):
    """Lägger in fordonsmodeller med intervall. Idempotent per märke+modell."""
    tillagda = 0
    for (marke, modell), intervall in MODELLER.items():
        finns = conn.execute(
            "SELECT 1 FROM fordonsmodeller "
            "WHERE marke=? AND modell=? AND (verkstad_id IS ? OR verkstad_id=?)",
            (marke, modell, verkstad_id, verkstad_id),
        ).fetchone()
        if finns:
            print(f"Hoppar över modell {marke} {modell} (finns redan)")
            continue
        cur = conn.execute(
            "INSERT INTO fordonsmodeller (marke, modell, arsmodell, verkstad_id) "
            "VALUES (?,?,?,?)",
            (marke, modell, None, verkstad_id),
        )
        fm_id = cur.lastrowid
        for service_typ, km in intervall.items():
            conn.execute(
                "INSERT OR REPLACE INTO fordonsmodell_intervall "
                "(fordonsmodell_id, service_typ, intervall_km, aktiv) VALUES (?,?,?,?)",
                (fm_id, service_typ, km, 1 if km else 0),
            )
        tillagda += 1
        print(f"La till modell {marke} {modell} ({len(intervall)} intervall)")
    return tillagda


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # Knyt bilarna till samma verkstad som första admin-användaren (ofta None)
    rad = conn.execute(
        "SELECT verkstad_id FROM anvandare ORDER BY id LIMIT 1"
    ).fetchone()
    verkstad_id = rad["verkstad_id"] if rad else None

    tillagda = 0
    for regnr, fnr, marke, modell, ar in BILAR:
        finns = conn.execute(
            "SELECT 1 FROM bilar WHERE regnr=? AND (verkstad_id IS ? OR verkstad_id=?)",
            (regnr, verkstad_id, verkstad_id),
        ).fetchone()
        if finns:
            print(f"Hoppar över {regnr} (finns redan)")
            continue

        cur = conn.execute(
            "INSERT INTO bilar (regnr,fordonsnummer,marke,modell,arsmodell,notering,verkstad_id) "
            "VALUES (?,?,?,?,?,?,?)",
            (regnr, fnr, marke, modell, ar, "Dummy-bil för test", verkstad_id),
        )
        bil_id = cur.lastrowid

        km = random.randint(20000, 180000)

        # En äldre servicepost så nedräkningarna blir meningsfulla
        service_km = max(km - random.randint(5000, 15000), 1000)
        conn.execute(
            "INSERT INTO handelser (bil_id,datum,km,typ,service_typer,beskrivning,skapad_av) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                bil_id,
                str(date.today() - timedelta(days=random.randint(30, 120))),
                service_km,
                "service",
                json.dumps(random.sample(SERVICE_TYPER, k=random.randint(1, 3))),
                "Service utförd",
                "Seed",
            ),
        )

        # Senaste milställning
        conn.execute(
            "INSERT INTO handelser (bil_id,datum,km,typ,service_typer,beskrivning,skapad_av) "
            "VALUES (?,?,?,?,?,?,?)",
            (bil_id, str(date.today()), km, "miltal", None, None, "Seed"),
        )
        tillagda += 1
        print(f"La till {regnr} ({marke} {modell}, {km} km)")

    modeller_tillagda = seed_fordonsbibliotek(conn, verkstad_id)

    conn.commit()
    conn.close()
    print(f"\nKlart: {tillagda} bilar och {modeller_tillagda} fordonsmodeller tillagda i {DB}")


if __name__ == "__main__":
    main()
