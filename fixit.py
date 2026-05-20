with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = "        try:\n            conn.execute(\"ALTER TABLE anvandare ADD COLUMN verkstad_id INTEGER\")\n        except: pass"

new = """        try:
            conn.execute("ALTER TABLE anvandare ADD COLUMN verkstad_id INTEGER")
        except: pass
        try:
            conn.execute("ALTER TABLE bilar ADD COLUMN verkstad_id INTEGER")
        except: pass"""

content = content.replace(old, new)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("KLART!" if new in content else "HITTADES INTE")