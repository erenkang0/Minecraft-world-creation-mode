#!/usr/bin/env python3
"""Uretilen mod verisini dogrular.

Kontroller:
  1. Tum JSON dosyalari gecerli mi.
  2. Referans butunlugu:
     - realisticworld: referanslarinin karsiligi mod dosyalarinda var mi.
     - minecraft: referanslari vanilla 26.2 verisinde var mi (--online ile
       mcmeta uzerinden HTTP kontrolu; yoksa yerel .cache ile sinirli).
  3. Sema kontrolu: uretilen dosyalardaki her {"type": ...} dugumunun anahtar
     kumesi, ayni tipin vanilla 26.2 verisindeki bir orneginin anahtar kumesiyle
     birebir eslesmeli (vanilla, sema icin referans kabul edilir).
  4. Spline sagligi: nokta konumlari artan sirada, offset degerleri makul aralikta.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "src/main/resources"
WG = RES / "data/realisticworld/worldgen"
REF_DIR = ROOT / ".cache/mcmeta-26.2"
MCMETA = "https://raw.githubusercontent.com/misode/mcmeta/26.2-data/data/minecraft/worldgen"

ID_RE = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_/.-]+$")
# Bu anahtarlarin string degerleri density function referansi DEGILDIR
NON_DF_KEYS = {"type", "noise", "random_name", "Name", "preset", "settings",
               "biome", "biome_is", "surface_type", "spline"}
# Bu anahtarlarin altindaki listeler referans listesi degildir (biyom vb.)
NON_DF_LIST_KEYS = {"values", "biome_is"}

errors = []
warnings = []


def err(msg):
    errors.append(msg)
    print(f"  HATA: {msg}")


def collect_refs(node, df_refs, noise_refs, parent_key=None):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and ID_RE.match(v):
                if k == "noise":
                    noise_refs.add(v)
                elif k not in NON_DF_KEYS:
                    df_refs.add(v)
            else:
                collect_refs(v, df_refs, noise_refs, k)
    elif isinstance(node, list):
        for v in node:
            if isinstance(v, str) and ID_RE.match(v) and parent_key not in NON_DF_LIST_KEYS:
                df_refs.add(v)
            else:
                collect_refs(v, df_refs, noise_refs, parent_key)


def collect_type_keysets(node, table):
    if isinstance(node, dict):
        t = node.get("type")
        if isinstance(t, str):
            table.setdefault(t, set()).add(frozenset(node.keys()))
        for v in node.values():
            collect_type_keysets(v, table)
    elif isinstance(node, list):
        for v in node:
            collect_type_keysets(v, table)


def check_splines(node, path="", value_range=None):
    """Spline konum siralamasini ve (verilirse) deger araligini dogrular.

    value_range yalnizca offset.json icin verilir: offset spline degerleri
    yukseklik uzayindadir (y ~= 63.5 + 128v). factor/jaggedness gibi
    fonksiyonlarin degerleri vanilla'da da genis araliklara cikar.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "points" and isinstance(v, list):
                locs = [p["location"] for p in v]
                if locs != sorted(locs):
                    err(f"{path}: spline konumlari sirali degil")
                for i, p in enumerate(v):
                    pv = p.get("value")
                    if isinstance(pv, (int, float)):
                        if value_range and not (value_range[0] <= pv <= value_range[1]):
                            err(f"{path}/points[{i}]: deger aralik disi: {pv}")
                    else:
                        check_splines(pv, f"{path}/points[{i}]/value", value_range)
            else:
                check_splines(v, f"{path}/{k}", value_range)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            check_splines(v, f"{path}[{i}]", value_range)


def http_exists(url, cache={}):
    if url in cache:
        return cache[url]
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req) as r:
            cache[url] = r.status == 200
    except Exception:
        cache[url] = False
    return cache[url]


def main():
    online = "--online" in sys.argv

    # 1. tum kaynak JSON'lar gecerli mi
    docs = {}
    for p in sorted(RES.rglob("*.json")) + [RES / "pack.mcmeta"]:
        try:
            docs[p] = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            err(f"{p.relative_to(ROOT)}: gecersiz JSON: {e}")
    print(f"{len(docs)} JSON dosyasi ayristirildi")
    if errors:
        sys.exit(1)

    # 2. referans butunlugu (worldgen dosyalari)
    df_refs, noise_refs = set(), set()
    for p, d in docs.items():
        if "worldgen" in str(p) and p.suffix == ".json" and "world_preset" not in str(p):
            collect_refs(d, df_refs, noise_refs)

    for ref in sorted(df_refs):
        ns, path = ref.split(":", 1)
        if ns == "realisticworld":
            f = WG / "density_function" / f"{path}.json"
            if not f.exists():
                err(f"eksik mod density function: {ref}")
        elif ns == "minecraft":
            local = REF_DIR / "density_function" / f"{path}.json"
            if local.exists():
                continue
            if online:
                if not http_exists(f"{MCMETA}/density_function/{path}.json"):
                    err(f"vanilla'da yok: density_function {ref}")
            else:
                warnings.append(f"cevrimdisi dogrulanamadi: {ref}")
    for ref in sorted(noise_refs):
        ns, path = ref.split(":", 1)
        if ns == "realisticworld":
            f = WG / "noise" / f"{path}.json"
            if not f.exists():
                err(f"eksik mod noise: {ref}")
        elif ns == "minecraft" and online:
            if not http_exists(f"{MCMETA}/noise/{path}.json"):
                err(f"vanilla'da yok: noise {ref}")
    print(f"{len(df_refs)} density function + {len(noise_refs)} noise referansi kontrol edildi")

    # 3. sema (anahtar kumesi) kontrolu — vanilla korpusuna karsi
    vanilla_types = {}
    for p in REF_DIR.rglob("*.json"):
        collect_type_keysets(json.loads(p.read_text()), vanilla_types)
    checked = 0
    for p, d in docs.items():
        if WG not in p.parents and not str(p).startswith(str(WG)):
            continue
        mine = {}
        collect_type_keysets(d, mine)
        for t, keysets in mine.items():
            if t not in vanilla_types:
                warnings.append(f"{p.name}: vanilla korpusunda ornegi olmayan tip: {t}")
                continue
            for ks in keysets:
                checked += 1
                if ks not in vanilla_types[t]:
                    err(f"{p.name}: {t} anahtarlari vanilla ornekleriyle uyusmuyor: "
                        f"{sorted(ks)}")
    print(f"{checked} tip dugumu vanilla semasina karsi kontrol edildi")

    # 4. spline sagligi
    for p, d in docs.items():
        if str(p).startswith(str(WG)):
            rng = (-0.45, 1.6) if p.name == "offset.json" else None
            check_splines(d, p.name, rng)
    print("spline kontrolu tamam")

    # world preset etiketi tutarliligi
    tag = docs[RES / "data/minecraft/tags/worldgen/world_preset/normal.json"]
    assert tag["values"] == ["realisticworld:realistic"] and tag["replace"] is False
    assert (WG / "world_preset/realistic.json").exists()
    preset = docs[WG / "world_preset/realistic.json"]
    assert preset["dimensions"]["minecraft:overworld"]["generator"]["settings"] \
        == "realisticworld:realistic"

    for w in warnings:
        print(f"  UYARI: {w}")
    if errors:
        print(f"\nBASARISIZ: {len(errors)} hata")
        sys.exit(1)
    print(f"\nTUM KONTROLLER GECTI ({len(warnings)} uyari)")


if __name__ == "__main__":
    main()
