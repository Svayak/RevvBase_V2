# Lokal utveckling

Kör RevvBase lokalt på din dator för att testa funktioner innan du pushar till GitHub.

## Snabbstart

```bash
cd ~/Claude/Projects/revvbase
./run-local.sh
```

Öppna sedan http://localhost:5001 i webbläsaren.

Första gången skapas automatiskt:
- en virtuell miljö (`venv/`) med alla beroenden
- en `.env` från `.env.example`
- en tom databas (`verkstad.db`)
- en standardanvändare: **admin / verkstad123**

Avsluta servern med `Ctrl+C`.

## Vad `run-local.sh` gör

1. Skapar `.env` från mallen om den saknas
2. Skapar/aktiverar `venv` och installerar `requirements.txt`
3. Laddar miljövariablerna från `.env`
4. Startar `python app.py`

Med `FLASK_DEBUG=1` (satt i `.env.example`) laddar servern om automatiskt när du sparar en fil.

## Testflöde: lokalt → GitHub

```bash
# 1. Testa lokalt
./run-local.sh          # verifiera i webbläsaren, Ctrl+C när klar

# 2. Committa när du är nöjd
git add -A
git commit -m "Beskriv ändringen"

# 3. Pusha
git push origin main
```

## Bra att veta

- `verkstad.db`, `.env`, `venv/` och `.backups/` ligger i `.gitignore` och pushas aldrig — din lokala testdata påverkar inte GitHub.
- Vill du börja om med tom databas: stäng servern och kör `rm verkstad.db`, starta sedan igen.
- Produktion körs via Gunicorn (`wsgi.py`), inte `app.py` direkt — de lokala port/debug-inställningarna påverkar därför inte servern i drift.
