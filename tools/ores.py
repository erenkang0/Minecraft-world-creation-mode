#!/usr/bin/env python3
"""Gercekci cevher dagilimi ureteci.

Vanilla 26.2 cevher placed_feature'larini (data/minecraft/worldgen/placed_feature/
ore_*.json) derinlige gore yeniden dagitacak sekilde gecersiz kilar (override).
Cikti minecraft ad alaninda yazilir; boylece TUM biyomlarda gecerli olur.

Mantik (gercek jeolojiyi taklit):
  - Demir: daglarda/yuksekte bol, ovada orta. `ore_iron_upper` say. artirilir.
  - Bakir: orta irtifada (dripstone kusagi) yogun.
  - Komur: yuzeye yakin bol.
  - Altin/kiziltas/lapis: derinlerde yogun; ust bantlar seyreltilir.
  - Elmas: yalnizca derin bantta (y < -32), buyuk damarlar dahil.
  - Zumrut: yuksek daglara ozgu kalir (say. hafif artar).
Sadece `count` ve `height_range` alanlari degistirilir; feature ve digerleri
vanilla'dan aynen korunur (codec uyumlulugu icin).

Kullanim: python3 tools/ores.py [--ref-dir DIR] [--fetch]
"""

import argparse
import copy
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "src/main/resources"
MCMETA = "https://raw.githubusercontent.com/misode/mcmeta/26.2-data/data/minecraft/worldgen/placed_feature"

# ore adi -> (yeni count | None, yeni yukseklik araligi | None)
# yukseklik: ("trapezoid"|"uniform", alt, ust) mutlak y; None ise dokunma.
TUNING = {
    # Demir: yuksek irtifada belirgin artis (daglar demir yatagi)
    "ore_iron_upper":     (140, ("trapezoid", 96, 384)),
    "ore_iron_middle":    (16,  ("trapezoid", -24, 72)),
    "ore_iron_small":     (12,  ("uniform", -64, 72)),
    # Bakir: dripstone/orta kusakta yogun
    "ore_copper":         (24,  ("trapezoid", -16, 112)),
    # Komur: yuzeye yakin bol
    "ore_coal_upper":     (40,  ("trapezoid", 128, 320)),
    "ore_coal_lower":     (32,  ("trapezoid", 0, 208)),
    # Altin: derin yogunluk
    "ore_gold":           (6,   ("trapezoid", -64, 24)),
    "ore_gold_lower":     (3,   ("uniform", -64, -32)),
    # Kiziltas: derinlerde bol
    "ore_redstone":       (10,  ("trapezoid", -64, 16)),
    "ore_redstone_lower": (10,  ("uniform", -64, -32)),
    # Lapis: derin bant
    "ore_lapis":          (8,   ("trapezoid", -64, 48)),
    # Elmas: yalnizca derin, buyuk damarlar guclendirilir
    "ore_diamond":        (9,   ("uniform", -64, -32)),
    "ore_diamond_medium": (3,   ("trapezoid", -64, -4)),
    "ore_diamond_large":  (1,   ("uniform", -64, -32)),
    "ore_diamond_buried": (6,   ("trapezoid", -64, -8)),
    # Zumrut: yuksek daglara ozgu, hafif artis
    "ore_emerald":        (120, ("trapezoid", 48, 480)),
}


def height_of(kind, lo, hi):
    if kind == "uniform":
        return {"type": "minecraft:uniform",
                "min_inclusive": {"absolute": lo},
                "max_inclusive": {"absolute": hi}}
    return {"type": "minecraft:trapezoid",
            "min_inclusive": {"absolute": lo},
            "max_inclusive": {"absolute": hi}}


def retune(doc, count, height):
    doc = copy.deepcopy(doc)
    for pl in doc["placement"]:
        t = pl.get("type")
        if t == "minecraft:count" and count is not None:
            pl["count"] = count
        elif t == "minecraft:height_range" and height is not None:
            pl["height"] = height_of(*height)
    return doc


def fetch_refs(ref_dir):
    for name in TUNING:
        dest = ref_dir / f"placed_feature/{name}.json"
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(f"{MCMETA}/{name}.json") as r:
            dest.write_bytes(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-dir", type=Path,
                    default=ROOT / ".cache/mcmeta-26.2/worldgen")
    ap.add_argument("--fetch", action="store_true")
    args = ap.parse_args()
    if args.fetch:
        fetch_refs(args.ref_dir)

    out_dir = RES / "data/minecraft/worldgen/placed_feature"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (count, height) in TUNING.items():
        src = args.ref_dir / f"placed_feature/{name}.json"
        doc = retune(json.loads(src.read_text()), count, height)
        (out_dir / f"{name}.json").write_text(json.dumps(doc, indent=2) + "\n")
        print(f"  yazildi: placed_feature/{name}.json (count={count})")
    print(f"{len(TUNING)} cevher yeniden dagitildi.")


if __name__ == "__main__":
    main()
