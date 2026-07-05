#!/usr/bin/env python3
"""Realistic World icin worldgen JSON ureteci.

Vanilla Minecraft 26.2 worldgen verisini (misode/mcmeta aynasi) temel alir,
uzerine asagidaki matematiksel donusumleri uygulayarak
`src/main/resources/data/realisticworld/worldgen/` altindaki dosyalari uretir.

Donusumler:
  ARAZI
  - Kitasallik/erozyon girdileri `_large` noise'lara gecirilir (4x buyuk kitalar).
  - Ridge noise xz olcegi 0.25 -> 0.18 (uzun, cizgisel siradaglar).
  - Offset spline'ina hipsometrik donusum: okyanuslar 1.6x derinlesir,
    ovalar (deger -0.15..0.25) aynen kalir, zirveler 1.28x yukselir (tavan 1.55).
    Yukseklik iliskisi: y ~= 63.5 + 128 * spline_degeri.
  - Jaggedness spline degerleri 1.35x (daha sivri zirveler).
  MAGARALAR
  - Peynir magarasi sapmasi 0.27 sabitinden derinlige bagli gradyana cevrilir
    (y=-64'te 0.05, y=32'de 0.27) -> derinlerde katedral boyutu kavernalar.
  - Magara girisleri: 0.37 -> 0.27 (daha buyuk/sik girisler).
  - Spagetti tunel kalinligi: -0.95/-0.35 -> -1.05/-0.40 (daha genis tuneller).
  - Noodle tunel kalinligi: -0.075/-0.025 -> -0.09/-0.035.
  - Sutun (pillar) nadirlik sabiti -1.0 -> -0.8 (kavernalarda daha cok dogal kolon).
  YUZEY / JEOLOJI (surface_rule)
  - Dik yamaclarda tas (falez gorunumu).
  - Irtifaya bagli kar cizgisi: y>=172 daimi kar, 144..172 arasi noise ile
    dalgali sinir, y>190 uzeri buzul (packed_ice) yamalari.
  - Kiyi bandinda (y 60..67) noise kapili genis kumsallar (altina kumtasi).
  - Ic kayacta derinlige gore bulanik sinirli jeolojik katmanlar:
    kalsit / andezit / granit / diyorit / tuf mercekleri.

Kullanim:
  python3 tools/generate.py [--ref-dir DIR] [--fetch]
  --fetch verilirse referanslar mcmeta'dan indirilir (internet gerekir).
"""

import argparse
import copy
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src/main/resources/data/realisticworld/worldgen"
MCMETA = "https://raw.githubusercontent.com/misode/mcmeta/26.2-data/data/minecraft/worldgen"

# Fork edilen (kopyalanip degistirilen) vanilla density function'lar.
# Degismeyen dosyalar (base_3d_noise, spaghetti_roughness_function, shift_x/z, y)
# fork edilmez; referanslar minecraft: ad alaninda kalir.
REF_MAP = {
    "minecraft:overworld/continents": "realisticworld:continents",
    "minecraft:overworld/erosion": "realisticworld:erosion",
    "minecraft:overworld/ridges": "realisticworld:ridges",
    "minecraft:overworld/ridges_folded": "realisticworld:ridges_folded",
    "minecraft:overworld/offset": "realisticworld:offset",
    "minecraft:overworld/factor": "realisticworld:factor",
    "minecraft:overworld/depth": "realisticworld:depth",
    "minecraft:overworld/jaggedness": "realisticworld:jaggedness",
    "minecraft:overworld/sloped_cheese": "realisticworld:sloped_cheese",
    "minecraft:overworld/caves/entrances": "realisticworld:caves/entrances",
    "minecraft:overworld/caves/spaghetti_2d": "realisticworld:caves/spaghetti_2d",
    "minecraft:overworld/caves/spaghetti_2d_thickness_modulator":
        "realisticworld:caves/spaghetti_2d_thickness_modulator",
    "minecraft:overworld/caves/pillars": "realisticworld:caves/pillars",
    "minecraft:overworld/caves/noodle": "realisticworld:caves/noodle",
}

VANILLA_FILES = [
    "noise_settings/overworld.json",
    "density_function/overworld/continents.json",
    "density_function/overworld/erosion.json",
    "density_function/overworld/ridges.json",
    "density_function/overworld/ridges_folded.json",
    "density_function/overworld/offset.json",
    "density_function/overworld/factor.json",
    "density_function/overworld/depth.json",
    "density_function/overworld/jaggedness.json",
    "density_function/overworld/sloped_cheese.json",
    "density_function/overworld/caves/entrances.json",
    "density_function/overworld/caves/spaghetti_2d.json",
    "density_function/overworld/caves/spaghetti_2d_thickness_modulator.json",
    "density_function/overworld/caves/pillars.json",
    "density_function/overworld/caves/noodle.json",
]

# ---------------------------------------------------------------- yardimcilar

def retarget(obj):
    """JSON agacindaki tum string referanslari REF_MAP'e gore degistirir."""
    if isinstance(obj, dict):
        return {k: retarget(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [retarget(v) for v in obj]
    if isinstance(obj, str):
        return REF_MAP.get(obj, obj)
    return obj


class Patcher:
    """Agacta kosula uyan dugumleri bulup degistirir; sayim tutarak dogrular."""

    def __init__(self, tree):
        self.tree = tree

    def replace(self, desc, match, apply, expected=1):
        count = self._walk(self.tree, match, apply)
        if count != expected:
            raise SystemExit(
                f"HATA: '{desc}' icin {expected} eslesme beklenirken {count} bulundu. "
                "Vanilla veri formati degismis olabilir.")
        return self

    def _walk(self, node, match, apply):
        count = 0
        if isinstance(node, dict):
            if match(node):
                apply(node)
                count += 1
            for v in node.values():
                count += self._walk(v, match, apply)
        elif isinstance(node, list):
            for v in node:
                count += self._walk(v, match, apply)
        return count


def is_noise(node, noise_id):
    return (isinstance(node, dict) and node.get("type") == "minecraft:noise"
            and node.get("noise") == noise_id)


def transform_spline_values(node, fn):
    """Spline noktalarindaki sayisal value/derivative alanlarina fn uygular.

    fn(value, derivative) -> (yeni_value, yeni_derivative)
    Ic ice spline'larda value bir spline objesi olabilir; o durumda recurse edilir.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "points" and isinstance(v, list):
                for pt in v:
                    val = pt.get("value")
                    if isinstance(val, (int, float)):
                        nv, nd = fn(val, pt.get("derivative", 0.0))
                        pt["value"], pt["derivative"] = nv, nd
                    else:
                        transform_spline_values(val, fn)
            else:
                transform_spline_values(v, fn)
    elif isinstance(node, list):
        for v in node:
            transform_spline_values(v, fn)


# ------------------------------------------------------- arazi donusumleri

# Hipsometrik egri: gercek Dunya'da karalarin cogu alcak ovadir, yuksek
# zirveler nadirdir; okyanus tabani ise kita sahanligindan sonra hizla derinlesir.
OCEAN_KNEE = -0.15      # bu degerin altindaki spline degerleri okyanus tabanidir
OCEAN_GAIN = 1.6        # okyanus derinlestirme carpani
PEAK_KNEE = 0.25        # bu degerin ustu daglik bolge
PEAK_GAIN = 1.28        # zirve yukseltme carpani
PEAK_CAP = 1.55         # tavan (y ~= 262 taban; jaggedness ustune eklenir)
JAGGEDNESS_GAIN = 1.35  # sivri zirve genligi carpani
RIDGE_XZ_SCALE = 0.18   # 0.25 -> daha uzun dalga boylu, cizgisel siradaglar


def hypsometric(v, d):
    if v < OCEAN_KNEE:
        return OCEAN_KNEE + (v - OCEAN_KNEE) * OCEAN_GAIN, d * OCEAN_GAIN
    if v > PEAK_KNEE:
        nv = PEAK_KNEE + (v - PEAK_KNEE) * PEAK_GAIN
        if nv >= PEAK_CAP:
            return PEAK_CAP, 0.0
        return nv, d * PEAK_GAIN
    return v, d


# ------------------------------------------------------------ surface rules

def block(name):
    return {"type": "minecraft:block", "result_state": {"Name": name}}


def cond(if_true, then_run):
    return {"type": "minecraft:condition", "if_true": if_true, "then_run": then_run}


def on_floor():
    return {"type": "minecraft:stone_depth", "offset": 0, "surface_type": "floor",
            "add_surface_depth": False, "secondary_depth_range": 0}


def under_floor(secondary=6):
    return {"type": "minecraft:stone_depth", "offset": 0, "surface_type": "floor",
            "add_surface_depth": True, "secondary_depth_range": secondary}


def y_above(y):
    return {"type": "minecraft:y_above", "anchor": {"absolute": y},
            "surface_depth_multiplier": 0, "add_stone_depth": False}


def noise_between(noise, lo, hi):
    return {"type": "minecraft:noise_threshold", "noise": noise,
            "min_threshold": lo, "max_threshold": hi}


def not_(c):
    return {"type": "minecraft:not", "invert": c}


def vgrad(name, true_below, false_above):
    return {"type": "minecraft:vertical_gradient", "random_name": name,
            "true_at_and_below": {"absolute": true_below},
            "false_at_and_above": {"absolute": false_above}}


def band(name, lo, hi, noise_cond, result, fuzz=4):
    """[lo, hi] araliginda, bulanik sinirli ve noise kapili jeolojik katman."""
    in_top = vgrad(f"realisticworld:{name}_top", hi - fuzz, hi + fuzz)
    below_bottom = vgrad(f"realisticworld:{name}_bottom", lo - fuzz, lo + fuzz)
    return cond(in_top, cond(not_(below_bottom), cond(noise_cond, result)))


def alpine_and_coast_rules():
    """Yuzeyin hemen ustunde calisan kurallar: falez, kar cizgisi, buzul, kumsal."""
    snow = block("minecraft:snow_block")
    return [
        # Dik yamaclar ciplak kaya (kar bile tutmaz)
        cond({"type": "minecraft:steep"}, cond(on_floor(), block("minecraft:stone"))),
        # y>190: buzul yamalari
        cond(y_above(190),
             cond(noise_between("realisticworld:snowline", 0.2, 10.0),
                  cond(on_floor(), block("minecraft:packed_ice")))),
        # Kar cizgisi: yukarida daimi, asagi indikce noise ile parcalanan sinir
        cond(y_above(172), cond(on_floor(), snow)),
        cond(y_above(158),
             cond(noise_between("realisticworld:snowline", -0.3, 10.0),
                  cond(on_floor(), snow))),
        cond(y_above(144),
             cond(noise_between("realisticworld:snowline", 0.3, 10.0),
                  cond(on_floor(), snow))),
        # Kiyi bandinda genis kumsallar (y 60..67, noise kapili), altinda kumtasi
        cond(y_above(60),
             cond(not_(y_above(67)),
                  cond(noise_between("realisticworld:beach", 0.1, 10.0),
                       {"type": "minecraft:sequence", "sequence": [
                           cond(on_floor(), block("minecraft:sand")),
                           cond(under_floor(), block("minecraft:sandstone")),
                       ]}))),
    ]


def strata_rules():
    """Ic kayacta jeolojik katmanlar; varsayilan tasin yerini yer yer alir."""
    return [
        band("calcite", 56, 74, noise_between("realisticworld:strata_a", 0.55, 10.0),
             block("minecraft:calcite")),
        band("andesite", 36, 58, noise_between("realisticworld:strata_a", -10.0, -0.35),
             block("minecraft:andesite")),
        band("granite", 12, 40, noise_between("realisticworld:strata_b", 0.4, 10.0),
             block("minecraft:granite")),
        band("diorite", 4, 24, noise_between("realisticworld:strata_b", -10.0, -0.45),
             block("minecraft:diorite")),
        band("tuff", 0, 12, noise_between("realisticworld:strata_a", 0.1, 0.6),
             block("minecraft:tuff")),
    ]


# ------------------------------------------------------------------- uretim

def load(ref_dir, rel):
    return json.loads((ref_dir / rel).read_text())


def dump(rel, obj):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")
    print(f"  yazildi: {path.relative_to(ROOT)}")


def fetch_refs(ref_dir):
    for rel in VANILLA_FILES:
        dest = ref_dir / rel
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"{MCMETA}/{rel}"
        print(f"  indiriliyor: {url}")
        with urllib.request.urlopen(url) as r:
            dest.write_bytes(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-dir", type=Path, default=ROOT / ".cache/mcmeta-26.2",
                    help="Vanilla 26.2 worldgen referans dizini")
    ap.add_argument("--fetch", action="store_true",
                    help="Eksik referanslari mcmeta'dan indir")
    args = ap.parse_args()

    if args.fetch:
        fetch_refs(args.ref_dir)
    missing = [f for f in VANILLA_FILES if not (args.ref_dir / f).exists()]
    if missing:
        raise SystemExit(
            f"Referans dosyalar eksik ({missing[0]} ...). --fetch ile indirin.")

    df = lambda name: load(args.ref_dir, f"density_function/overworld/{name}.json")

    # --- continents / erosion: 4x buyuk kitalar icin _large noise'lar
    continents = df("continents")
    Patcher(continents).replace(
        "continentalness -> continentalness_large",
        lambda n: n.get("noise") == "minecraft:continentalness",
        lambda n: n.__setitem__("noise", "minecraft:continentalness_large"))
    dump("density_function/continents.json", retarget(continents))

    erosion = df("erosion")
    Patcher(erosion).replace(
        "erosion -> erosion_large",
        lambda n: n.get("noise") == "minecraft:erosion",
        lambda n: n.__setitem__("noise", "minecraft:erosion_large"))
    dump("density_function/erosion.json", retarget(erosion))

    # --- ridges: cizgisel siradaglar icin daha buyuk dalga boyu
    ridges = df("ridges")
    Patcher(ridges).replace(
        "ridge xz_scale 0.25 -> %s" % RIDGE_XZ_SCALE,
        lambda n: n.get("noise") == "minecraft:ridge" and n.get("xz_scale") == 0.25,
        lambda n: n.__setitem__("xz_scale", RIDGE_XZ_SCALE))
    dump("density_function/ridges.json", retarget(ridges))
    dump("density_function/ridges_folded.json", retarget(df("ridges_folded")))

    # --- offset: hipsometrik yukseklik dagilimi
    offset = df("offset")
    transform_spline_values(offset, hypsometric)
    dump("density_function/offset.json", retarget(offset))

    # --- jaggedness: daha sivri zirveler
    jaggedness = df("jaggedness")
    transform_spline_values(
        jaggedness, lambda v, d: (v * JAGGEDNESS_GAIN, d * JAGGEDNESS_GAIN))
    dump("density_function/jaggedness.json", retarget(jaggedness))

    # --- degismeden fork edilenler (sadece referanslari guncellenir)
    dump("density_function/factor.json", retarget(df("factor")))
    dump("density_function/depth.json", retarget(df("depth")))
    dump("density_function/sloped_cheese.json", retarget(df("sloped_cheese")))

    # --- magaralar
    entrances = df("caves/entrances")
    Patcher(entrances).replace(
        "magara giris esigi 0.37 -> 0.27",
        lambda n: n.get("argument1") == 0.37 and is_noise(
            n.get("argument2"), "minecraft:cave_entrance"),
        lambda n: n.__setitem__("argument1", 0.27))
    dump("density_function/caves/entrances.json", retarget(entrances))

    thickness = df("caves/spaghetti_2d_thickness_modulator")
    Patcher(thickness).replace(
        "spagetti kalinligi -0.95 -> -1.05",
        lambda n: n.get("argument1") == -0.95,
        lambda n: n.__setitem__("argument1", -1.05)
    ).replace(
        "spagetti kalinlik genligi -0.35 -> -0.40",
        lambda n: n.get("argument1") == -0.35000000000000003 and is_noise(
            n.get("argument2"), "minecraft:spaghetti_2d_thickness"),
        lambda n: n.__setitem__("argument1", -0.4))
    dump("density_function/caves/spaghetti_2d_thickness_modulator.json",
         retarget(thickness))

    dump("density_function/caves/spaghetti_2d.json", retarget(df("caves/spaghetti_2d")))

    noodle = df("caves/noodle")
    Patcher(noodle).replace(
        "noodle kalinligi -0.075 -> -0.09",
        lambda n: n.get("argument1") == -0.07500000000000001,
        lambda n: n.__setitem__("argument1", -0.09)
    ).replace(
        "noodle kalinlik genligi -0.025 -> -0.035",
        lambda n: n.get("argument1") == -0.025 and is_noise(
            n.get("argument2"), "minecraft:noodle_thickness"),
        lambda n: n.__setitem__("argument1", -0.035))
    dump("density_function/caves/noodle.json", retarget(noodle))

    pillars = df("caves/pillars")
    Patcher(pillars).replace(
        "sutun nadirligi -1.0 -> -0.8",
        lambda n: (n.get("argument1") == -1.0 and isinstance(n.get("argument2"), dict)
                   and is_noise(n["argument2"].get("argument2"), "minecraft:pillar_rareness")),
        lambda n: n.__setitem__("argument1", -0.8))
    dump("density_function/caves/pillars.json", retarget(pillars))

    # --- noise_settings
    settings = load(args.ref_dir, "noise_settings/overworld.json")

    router = settings["noise_router"]
    Patcher(router).replace(
        "iklim: temperature -> temperature_large",
        lambda n: n.get("noise") == "minecraft:temperature",
        lambda n: n.__setitem__("noise", "minecraft:temperature_large")
    ).replace(
        "iklim: vegetation -> vegetation_large",
        lambda n: n.get("noise") == "minecraft:vegetation",
        lambda n: n.__setitem__("noise", "minecraft:vegetation_large")
    ).replace(
        "peynir magarasi sapmasi 0.27 -> derinlik gradyani",
        lambda n: n.get("argument1") == 0.27 and is_noise(
            n.get("argument2"), "minecraft:cave_cheese"),
        lambda n: n.__setitem__("argument1", {
            "type": "minecraft:y_clamped_gradient",
            "from_y": -64, "from_value": 0.05,
            "to_y": 32, "to_value": 0.27,
        }))

    # Yuzey kurallari: [bedrock, YENI alpin/kiyi, vanilla..., YENI jeoloji]
    sr = settings["surface_rule"]
    seq = sr["sequence"]
    if "bedrock" not in json.dumps(seq[0]):
        raise SystemExit("HATA: surface_rule[0] bedrock kurali degil.")
    aps = {"type": "minecraft:above_preliminary_surface"}
    ours = cond(aps, {"type": "minecraft:sequence", "sequence": alpine_and_coast_rules()})
    sr["sequence"] = [seq[0], ours] + seq[1:] + strata_rules()

    settings = retarget(settings)
    dump("noise_settings/realistic.json", settings)
    print("Tamamlandi.")


if __name__ == "__main__":
    main()
