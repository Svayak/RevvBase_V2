with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '<form method="post"><input type="password" name="password" placeholder="Lösenord" autofocus><button>Logga in</button></form>'
new = '<form method="post"><input type="hidden" name="csrf_token" value="\' + csrf_token() + \'"><input type="password" name="password" placeholder="Lösenord" autofocus><button>Logga in</button></form>'

content = content.replace(old, new)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("KLART!")