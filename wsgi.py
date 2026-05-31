import os
import threading
os.makedirs('/home/data', exist_ok=True)

from app import app, init_db, get_db, daglig_backup
from werkzeug.security import generate_password_hash

init_db()

# Starta backup-tråd (körs av Gunicorn, inte bara vid direktkörning)
t = threading.Thread(target=daglig_backup, daemon=True)
t.start()

with get_db() as conn:
    count = conn.execute("SELECT COUNT(*) FROM anvandare").fetchone()[0]
if count == 0:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO anvandare (username, namn, password_hash, roll) VALUES (?,?,?,?)",
            ("admin", "Admin", generate_password_hash("verkstad123", method="pbkdf2:sha256"), "admin")
        )

if __name__ == '__main__':
    app.run()