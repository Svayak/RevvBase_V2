# Kör från ~/RevvBase_V2:
# python3 patch_superadmin_paketlank.py

with open('templates/superadmin.html', 'r', encoding='utf-8') as f:
    content = f.read()

old = """      <form method="post" action="/superadmin/backup">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button type="submit" class="btn-ghost">💾 Backup alla</button>
      </form>
      <button class="btn-primary" onclick="oppnaModal('nyModal')">+ Lägg till kund</button>"""

new = """      <a href="/superadmin/paket" class="btn-ghost">⚙ Paketinställningar</a>
      <form method="post" action="/superadmin/backup">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <button type="submit" class="btn-ghost">💾 Backup alla</button>
      </form>
      <button class="btn-primary" onclick="oppnaModal('nyModal')">+ Lägg till kund</button>"""

if old not in content:
    print("FEL: Hittade inte ankaret i superadmin.html")
else:
    content = content.replace(old, new)
    with open('templates/superadmin.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✓ KLART!")
