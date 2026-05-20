with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = 'DB = os.path.join(os.path.dirname(__file__), "verkstad.db")'
new = 'DB = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "verkstad.db"))'

if old in content:
    content = content.replace(old, new)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("KLART! DB_PATH uppdaterad i app.py")
else:
    print("Hittade inte strängen - kolla app.py manuellt")