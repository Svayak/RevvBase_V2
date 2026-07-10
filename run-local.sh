#!/usr/bin/env bash
# Startar RevvBase lokalt för test innan push.
# Skapar venv + installerar beroenden vid första körningen.
# Användning:  ./run-local.sh
set -euo pipefail
cd "$(dirname "$0")"

# 1. Skapa .env från mall om den saknas
if [ ! -f .env ]; then
  echo "Skapar .env från .env.example"
  cp .env.example .env
fi

# 2. Skapa/aktivera virtuell miljö
if [ ! -d venv ]; then
  echo "Skapar virtuell miljö (venv)..."
  python3 -m venv venv
fi
source venv/bin/activate

# 3. Installera beroenden
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 4. Ladda miljövariabler från .env
set -a
# shellcheck disable=SC1091
source .env
set +a

# 5. Starta servern
echo ""
echo "Startar RevvBase på http://localhost:${PORT:-5001}"
echo "Standardinlogg (skapas vid första start): admin / verkstad123"
echo "Avsluta med Ctrl+C."
echo ""
python app.py
