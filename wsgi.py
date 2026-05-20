import os
os.makedirs('/home/data', exist_ok=True)

from app import app, init_db, get_db
from werkzeug.security import generate_password_hash

init_db()

with get_db() as conn:
    count = conn.execute("SELECT COUNT(*) FROM anvandare").fetchone()[0]
if count == 0:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO anvandare (username, namn, password_hash, roll) VALUES (?,?,?,?)",
            ("admin", "Admin", generate_password_hash("verkstad123"), "admin")
        )

if __name__ == '__main__':
    app.run()