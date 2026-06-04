import shutil, py_compile

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

shutil.copy('app.py', 'app.py.bak')
print("Backup: app.py.bak")

changes = 0

# ── 1. bygg_panel: hoppa över typer utan intervall (iv=None) ─────────────────
old = '''    panel = {}
    for t, info in intervaller.items():
        if not info["aktiv"]:
            continue
        iv = info["intervall"]
        if t in senaste_per_typ:
            diff = (senaste_km - senaste_per_typ[t]) if senaste_km is not None else None
            aldrig_gjort = False
        else:
            diff = senaste_km if senaste_km is not None else None
            aldrig_gjort = True
        panel[t] = {"diff": diff, "intervall": iv, "aldrig_gjort": aldrig_gjort}
    return panel'''

new = '''    panel = {}
    for t, info in intervaller.items():
        if not info["aktiv"]:
            continue
        iv = info["intervall"]
        # Ingen km angiven = visa inte på bilkortet
        if iv is None:
            continue
        if t in senaste_per_typ:
            diff = (senaste_km - senaste_per_typ[t]) if senaste_km is not None else None
            aldrig_gjort = False
        else:
            diff = senaste_km if senaste_km is not None else None
            aldrig_gjort = True
        panel[t] = {"diff": diff, "intervall": iv, "aldrig_gjort": aldrig_gjort}
    return panel'''

if old in content:
    content = content.replace(old, new, 1)
    changes += 1
    print("✓ 1. bygg_panel: servicetyper utan km döljs")
else:
    print("✗ 1. bygg_panel — HITTADES INTE")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

# ── 2. bil.html: ta bort Kedjedrift-fallback ──────────────────────────────────
with open('templates/bil.html', 'r', encoding='utf-8') as f:
    html = f.read()

old_html = '''      {% if iv is none %}
        <div class="mil-card__value">–</div>
        <div class="mil-card__sub">Kedjedrift</div>
      {% else %}
        <div class="mil-card__value">{{ diff if diff is not none else '?' }}</div>
        <div class="mil-card__sub">/ {{ iv }} km{% if aldrig %}*{% endif %}</div>
      {% endif %}'''

new_html = '''      <div class="mil-card__value">{{ diff if diff is not none else '?' }}</div>
      <div class="mil-card__sub">/ {{ iv }} km{% if aldrig %}*{% endif %}</div>'''

if old_html in html:
    html = html.replace(old_html, new_html, 1)
    changes += 1
    print("✓ 2. bil.html: Kedjedrift-fallback borttagen")
else:
    print("✗ 2. bil.html Kedjedrift — HITTADES INTE")

with open('templates/bil.html', 'w', encoding='utf-8') as f:
    f.write(html)

try:
    py_compile.compile('app.py', doraise=True)
    print(f"\n✓ Syntax OK — {changes}/2 ändringar applicerade")
    print("\nKör nu:")
    print("  git add . && git commit -m 'Fix: dölj servicetyper utan km från bilkortet' && git push")
except py_compile.PyCompileError as e:
    print(f"\n✗ SYNTAXFEL: {e}")
    shutil.copy('app.py.bak', 'app.py')
    print("Återställde app.py från backup")
