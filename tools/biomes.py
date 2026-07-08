#!/usr/bin/env python3
"""Ozel biyom (yuzey + magara) ureteci ve overworld enjeksiyonu.

Uc yuzey + iki magara biyomu tanimlar, bunlari vanilla biyomlardan tureterek
26.2 codec'iyle uyumlu tutar (yalnizca renk/iklim/oznitelik degistirir, yeni
sema alani icat etmez). Ardindan bayrak preset'i olan `realistic`in overworld
multi_noise kaynagini, vanilla parametre listesine (tools/refs/
overworld_biome_parameters.json) ozel biyom parametre noktalari eklenmis
ACIK bir liste ile degistirir.

Yontem:
  - Yuzey biyomu: secilen iklim nisi icin depth=0.0 ve depth=1.0 cifti eklenir.
  - Magara biyomu: depth=[0.2, 0.9] tek giris (vanilla dripstone/lush gibi).
Parametre noktasi EKLEMEK bosluk yaratmaz (en yakin nokta kazanir), bu yuzden
kayit yuklemesi guvenlidir; ozel biyomlar kendi nislerinin yakininda belirir.

Varyant dunya turleri (islands/pangaea/canyons) vanilla biyom preset'ini
kullanmaya devam eder; ozel biyomlar bayrak "Gerçekçi Dünya"da yer alir.

Kullanim: python3 tools/biomes.py [--ref-dir DIR]
"""

import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "src/main/resources"
BIOME_OUT = RES / "data/realisticworld/worldgen/biome"
PRESET = RES / "data/realisticworld/worldgen/world_preset/realistic.json"
PARAMS = ROOT / "tools/refs/overworld_biome_parameters.json"


def set_sky(biome, hex_color):
    biome.setdefault("attributes", {})["minecraft:visual/sky_color"] = hex_color


# ------------------------------------------------------- ozel biyom tanimlari
# Her giris: kaynak vanilla biyom + iklim/renk degisiklikleri + iklim nisi.
# Iklim nisi: her parametre icin [lo, hi] (depth haric; kod tarafindan atanir).
# Renkler vanilla format (tamsayi 0xRRGGBB).

SURFACE_BIOMES = {
    # id: (kaynak, {temp,downfall,precip}, {effects...}, sky, iklim_nisi)
    "high_steppe": dict(
        base="meadow",
        set=dict(temperature=0.7, downfall=0.2, has_precipitation=True),
        effects=dict(grass_color="#a6a94a", foliage_color="#8fa83c",
                     water_color="#4e7fcf"),
        sky="#8fb6ff",
        niche=dict(temperature=[0.15, 0.55], humidity=[-0.7, -0.2],
                   continentalness=[0.3, 1.0], erosion=[-0.5, -0.05],
                   weirdness=[-1.0, 1.0]),
    ),
    "misty_valley": dict(
        base="taiga",
        set=dict(temperature=0.15, downfall=0.9, has_precipitation=True),
        effects=dict(grass_color="#5e7d5a", foliage_color="#4a6b48",
                     water_color="#3d5a6b"),
        sky="#8a97a3",
        niche=dict(temperature=[-0.15, 0.25], humidity=[0.3, 0.75],
                   continentalness=[0.1, 0.8], erosion=[0.3, 1.0],
                   weirdness=[-1.0, 1.0]),
    ),
    "volcanic_region": dict(
        base="stony_peaks",
        set=dict(temperature=2.0, downfall=0.0, has_precipitation=False),
        effects=dict(water_color="#4c3a2a"),
        sky="#6b4a3a",
        niche=dict(temperature=[0.55, 1.0], humidity=[-1.0, -0.35],
                   continentalness=[0.55, 1.0], erosion=[-1.0, -0.4],
                   weirdness=[0.1, 1.0]),
    ),
}

CAVE_BIOMES = {
    "giant_dripstone": dict(
        base="dripstone_caves",
        set={},
        effects=dict(water_color="#4a5560"),
        sky="#000000",
        niche=dict(temperature=[-1.0, 1.0], humidity=[-1.0, 1.0],
                   continentalness=[0.2, 0.75], erosion=[-1.0, 1.0],
                   weirdness=[-1.0, 1.0]),
    ),
    "crystal_caves": dict(
        base="lush_caves",
        set={},
        effects=dict(water_color="#8a5cd0", grass_color="#b07ce0",
                     foliage_color="#9a6cd8"),
        sky="#000000",
        niche=dict(temperature=[-0.6, -0.1], humidity=[-0.35, 0.3],
                   continentalness=[-1.0, 1.0], erosion=[-1.0, 1.0],
                   weirdness=[-1.0, 1.0]),
    ),
}


def build_biome(base_dir, spec):
    b = copy.deepcopy(json.loads((base_dir / f"{spec['base']}.json").read_text()))
    for k, v in spec["set"].items():
        b[k] = v
    for k, v in spec["effects"].items():
        b["effects"][k] = v          # renkler "#RRGGBB" string (vanilla format)
    set_sky(b, spec["sky"])
    return b


def param_entry(biome_id, niche, depth):
    p = {"temperature": niche["temperature"], "humidity": niche["humidity"],
         "continentalness": niche["continentalness"], "erosion": niche["erosion"],
         "weirdness": niche["weirdness"], "depth": depth, "offset": 0.0}
    return {"biome": biome_id, "parameters": p}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-dir", type=Path, default=ROOT / ".cache/mcmeta-26.2")
    args = ap.parse_args()
    base_dir = args.ref_dir / "biome_bases"

    BIOME_OUT.mkdir(parents=True, exist_ok=True)
    added = []

    # yuzey biyomlari: depth 0.0 + 1.0 cifti
    for bid, spec in SURFACE_BIOMES.items():
        biome = build_biome(base_dir, spec)
        (BIOME_OUT / f"{bid}.json").write_text(json.dumps(biome, indent=2) + "\n")
        print(f"  yazildi: biome/{bid}.json (kaynak {spec['base']})")
        ref = f"realisticworld:{bid}"
        added.append(param_entry(ref, spec["niche"], 0.0))
        added.append(param_entry(ref, spec["niche"], 1.0))

    # magara biyomlari: depth [0.2, 0.9]
    for bid, spec in CAVE_BIOMES.items():
        biome = build_biome(base_dir, spec)
        (BIOME_OUT / f"{bid}.json").write_text(json.dumps(biome, indent=2) + "\n")
        print(f"  yazildi: biome/{bid}.json (kaynak {spec['base']})")
        ref = f"realisticworld:{bid}"
        added.append(param_entry(ref, spec["niche"], [0.2, 0.9]))

    # vanilla parametre listesine ekle ve bayrak preset'ine ACIK liste yaz
    vanilla = json.loads(PARAMS.read_text())["biomes"]
    full_list = vanilla + added
    preset = json.loads(PRESET.read_text())
    ow = preset["dimensions"]["minecraft:overworld"]["generator"]
    ow["biome_source"] = {"type": "minecraft:multi_noise", "biomes": full_list}
    # acik liste buyuk oldugu icin minified yazilir (jar boyutu)
    PRESET.write_text(json.dumps(preset, separators=(",", ":")) + "\n")
    print(f"  realistic preset overworld kaynagi acik listeye cevrildi "
          f"({len(vanilla)} vanilla + {len(added)} ozel giris)")
    print("Ozel biyomlar tamamlandi.")


if __name__ == "__main__":
    main()
