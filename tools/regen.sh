#!/usr/bin/env bash
# Tum worldgen verisini vanilla 26.2 referanslarindan yeniden uretir.
# SIRA ONEMLI: generate.py bayrak preset'ini yazar; biomes.py o preset'in
# biyom kaynagini ozel biyomlarla ACIK listeye cevirir (en son calismali).
set -euo pipefail
cd "$(dirname "$0")/.."

FETCH="${1:-}"   # ilk kez calistiriyorsan: ./tools/regen.sh --fetch

python3 tools/generate.py $FETCH    # arazi + magaralar + dunya turleri
python3 tools/villages.py $FETCH    # buyuk koyler (meydan + binalar + havuzlar)
python3 tools/ores.py     $FETCH    # gercekci cevher dagilimi
python3 tools/biomes.py             # ozel biyomlar (preset'i acik listeye cevirir)

python3 tools/validate.py --online
echo "Yeniden uretim tamam."
