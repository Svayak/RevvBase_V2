with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Ta bort den gamla /landing-routen vi lade till tidigare
old_landing = """
@app.route('/landing')
def landing():
    return open('landing.html', encoding='utf-8').read()

"""
content = content.replace(old_landing, "")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("KLART!")