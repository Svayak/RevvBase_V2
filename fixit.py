with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''    return """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>SuperAdmin Login</title>
    <style>*{box-sizing:border-box;margin:0;padding:0}body{background:#0f1113;color:#e8eaec;font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}.box{background:#181b1e;border:1px solid #2e3338;border-radius:10px;padding:2rem;width:340px}.logo{font-size:1.8rem;font-weight:900;color:#f0a500;text-align:center;margin-bottom:1.5rem}input{width:100%;background:#22262b;border:1px solid #2e3338;border-radius:6px;color:#e8eaec;padding:.7rem;font-size:1rem;margin-bottom:1rem}button{width:100%;background:#f0a500;color:#000;border:none;border-radius:6px;padding:.75rem;font-weight:700;font-size:1rem;cursor:pointer}.err{color:#e05050;font-size:.85rem;margin-bottom:1rem}</style></head>
    <body><div class="box"><div class="logo">REVVBASE ADMIN</div>""" + (f\'<div class="err">{error}</div>\' if error else "") + """<form method="post"><input type="hidden" name="csrf_token" value="\' + csrf_token() + \'"><input type="password" name="password" placeholder="Lösenord" autofocus><button>Logga in</button></form></div></body></html>"""'''

new = '    return render_template("superadmin_login.html", error=error)'

content = content.replace(old, new)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

if new in content:
    print("KLART!")
else:
    print("HITTADE INTE STRÄNGEN - behöver fixas manuellt")