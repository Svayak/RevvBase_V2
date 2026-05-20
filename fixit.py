with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Gör landningssidan till startsidan
old_index = """@app.route("/")
@login_required
def index():"""

new_index = """@app.route("/landing_old")
@login_required
def index():"""

# 2. Lägg till landningssida som startsida
landing_route = """
@app.route("/")
def landing():
    from flask_login import current_user
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    return open('landing.html', encoding='utf-8').read()

"""

content = content.replace(old_index, landing_route + old_index.replace('"/>"', '"/"').replace('@app.route("/")', '@app.route("/dashboard")'))

# Fixa index-routen till /dashboard
content = content.replace('@app.route("/landing_old")\n@login_required\ndef index():', '@app.route("/dashboard")\n@login_required\ndef index():')

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("KLART!")