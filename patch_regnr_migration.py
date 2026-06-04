# Kör detta från ~/RevvBase_V2:
# python3 patch_regnr_migration.py

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Ändra CREATE TABLE bilar - ta bort UNIQUE på regnr
old_create = """            CREATE TABLE IF NOT EXISTS bilar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                regnr TEXT NOT NULL UNIQUE,"""

new_create = """            CREATE TABLE IF NOT EXISTS bilar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                regnr TEXT NOT NULL,"""

# 2. Migration som körs vid uppstart
old_migration = """        try:
            conn.execute("ALTER TABLE anvandare ADD COLUMN senaste_inloggning TEXT")
        except: pass"""

new_migration = """        try:
            conn.execute("ALTER TABLE anvandare ADD COLUMN senaste_inloggning TEXT")
        except: pass
        # Migration: byt UNIQUE(regnr) mot UNIQUE(regnr, verkstad_id)
        try:
            conn.executescript(\"\"\"
                CREATE TABLE IF NOT EXISTS bilar_ny (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    regnr TEXT NOT NULL,
                    fordonsnummer TEXT,
                    marke TEXT NOT NULL,
                    modell TEXT NOT NULL,
                    arsmodell INTEGER,
                    notering TEXT,
                    verkstad_id INTEGER,
                    UNIQUE(regnr, verkstad_id)
                );
                INSERT OR IGNORE INTO bilar_ny SELECT * FROM bilar;
                DROP TABLE bilar;
                ALTER TABLE bilar_ny RENAME TO bilar;
            \"\"\")
        except Exception as e:
            print(f"Migration bilar: {e}")"""

if old_create not in content:
    print("FEL: Hittade inte CREATE TABLE bilar-strängen — kontrollera app.py")
elif old_migration not in content:
    print("FEL: Hittade inte migration-ankaret — kontrollera app.py")
else:
    content = content.replace(old_create, new_create)
    content = content.replace(old_migration, new_migration)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ KLART! Kör nu:")
    print("  python3 -c \"import py_compile; py_compile.compile('app.py', doraise=True)\" && echo '✓ OK'")
    print("  git add app.py")
    print("  git commit -m 'Fix: UNIQUE(regnr, verkstad_id) — samma regnr tillåts i olika verkstäder'")
    print("  git push")
