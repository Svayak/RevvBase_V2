import os
import fcntl
import threading

# /home/data är Azures persistenta lagring. Lokalt (och i test) finns den inte och
# går inte att skapa — det ska inte hindra appen från att starta.
try:
    os.makedirs('/home/data', exist_ok=True)
except OSError as e:
    print(f"Kunde inte skapa /home/data ({e}) — fortsätter utan.")

from app import app, init_db, get_db, daglig_backup, BACKUP_DIR
from werkzeug.security import generate_password_hash

init_db()

# Håll fillåset öppet processen ut — stängs filen släpps låset.
_backup_lock_fil = None

def starta_backup_en_gang():
    """Startar backup-tråden i exakt EN Gunicorn-worker.

    Tidigare startade varje worker en egen tråd, som alla skrev till samma
    CSV-filer samtidigt. Ett icke-blockerande fillås gör att bara den första
    workern vinner; övriga hoppar över.
    """
    global _backup_lock_fil
    las_sokvag = os.path.join(BACKUP_DIR, ".backup.lock")
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        f = open(las_sokvag, "w")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # En annan worker håller låset (eller mappen går inte att skriva till)
        return False
    _backup_lock_fil = f
    threading.Thread(target=daglig_backup, daemon=True).start()
    return True

starta_backup_en_gang()

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
