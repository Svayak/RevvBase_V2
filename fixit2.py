import shutil, py_compile

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

shutil.copy('app.py', 'app.py.bak')
print("Backup: app.py.bak")

old = '''    for t in NEDRAKNARE_TYPER:
        if t in db_map:
            r = db_map[t]
            result[t] = {"intervall": r["intervall_km"], "aktiv": bool(r["aktiv"]), "egen": False}
        elif t in standard:
            result[t] = {"intervall": standard[t], "aktiv": standard[t] is not None, "egen": False}'''

new = '''    for t in NEDRAKNARE_TYPER:
        if t in db_map:
            r = db_map[t]
            result[t] = {"intervall": r["intervall_km"], "aktiv": bool(r["aktiv"]), "egen": False}
        elif t in standard:
            std = standard[t]
            # standard[t] kan vara en dict (från fordonsmodell_intervall) eller ett heltal (från STANDARD_INTERVALL)
            if isinstance(std, dict):
                iv_km = std.get("intervall")
                iv_aktiv = std.get("aktiv", True)
            else:
                iv_km = std
                iv_aktiv = std is not None
            result[t] = {"intervall": iv_km, "aktiv": iv_aktiv, "egen": False}'''

if old in content:
    content = content.replace(old, new, 1)
    print("✓ get_intervall nested dict-bug fixad")
else:
    print("✗ Hittades inte — kontrollera manuellt")

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

try:
    py_compile.compile('app.py', doraise=True)
    print("✓ Syntax OK")
    print("\nKör nu:")
    print("  git add . && git commit -m 'Fix: serviceintervall visas som dict istället för km' && git push")
except py_compile.PyCompileError as e:
    print(f"✗ SYNTAXFEL: {e}")
    shutil.copy('app.py.bak', 'app.py')
    print("Återställde app.py från backup")
