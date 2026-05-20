with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

route = """
@app.route('/')
def landing():
    return open('landing.html', encoding='utf-8').read()

"""

content = content.replace("# ── ROUTES ──", route + "# ── ROUTES ──")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("KLART!")