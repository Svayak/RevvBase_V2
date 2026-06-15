import shutil

with open('templates/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

shutil.copy('templates/index.html', 'templates/index.html.bak')
print("Backup: templates/index.html.bak")

changes = 0

# ── 1. Sökformulär + rensa-knapp: skicka till nuvarande sida (behåller slug + query) ──
old1 = '''  <form class="search-form" method="get" action="{{ url_for('index') }}">
    <input class="search-input" type="text" name="q" value="{{ q }}" placeholder="Sök reg.nr, fordonsnr, märke…" autocomplete="off">
    {% if q %}<a href="{{ url_for('index') }}" class="clear-search">✕</a>{% endif %}
  </form>'''
new1 = '''  <form class="search-form" method="get" action="{{ request.path }}">
    <input class="search-input" type="text" name="q" value="{{ q }}" placeholder="Sök reg.nr, fordonsnr, märke…" autocomplete="off">
    {% if q %}<a href="{{ request.path }}" class="clear-search">✕</a>{% endif %}
  </form>'''
if old1 in html:
    html = html.replace(old1, new1, 1)
    changes += 1
    print("✓ 1. Sökformulär + rensa-knapp skickar nu till request.path")
else:
    print("✗ 1. Sökformulär — HITTADES INTE")

# ── 2. "Visa alla"-länk i empty-state: samma sida utan query ──────────────────
old2 = '''    <p>Inga bilar matchade sökningen.</p>
    <a href="{{ url_for('index') }}" class="btn btn-ghost">Visa alla</a>'''
new2 = '''    <p>Inga bilar matchade sökningen.</p>
    <a href="{{ request.path }}" class="btn btn-ghost">Visa alla</a>'''
if old2 in html:
    html = html.replace(old2, new2, 1)
    changes += 1
    print("✓ 2. 'Visa alla'-länk pekar nu på request.path")
else:
    print("✗ 2. 'Visa alla'-länk — HITTADES INTE")

with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"\n✓ Klart — {changes}/2 ändringar applicerade")
print("(Endast template ändrad, ingen Python — inget py_compile behövs)")
print("\nKör nu:")
print("  git add . && git commit -m 'Fix: sok behaller slug + sokterm' && git push")
