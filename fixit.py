with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Lägg till verkstader-tabell i init_db
old_table = '''        conn.executescript("""
            CREATE TABLE IF NOT EXISTS kommentarer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bil_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                skapad_av TEXT,
                datum TEXT NOT NULL,
                FOREIGN KEY (bil_id) REFERENCES bilar(id)
            );
        """)'''

new_table = '''        conn.executescript("""
            CREATE TABLE IF NOT EXISTS kommentarer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bil_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                skapad_av TEXT,
                datum TEXT NOT NULL,
                FOREIGN KEY (bil_id) REFERENCES bilar(id)
            );
        """)
        conn.executescript("""
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
        except: pass'''

content = content.replace(old_table, new_table)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("KLART!")