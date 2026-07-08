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
  5. Koy dosyalari: NBT sablonlari cozumlenebilir mi (boyut/palet/jigsaw
     tutarliligi), havuzlarin location referanslarinin NBT karsiliklari var mi,
     yapi tanimlari codec sinirlarinda mi (size 0..7, mesafe 1..128), NBT
     icindeki jigsaw havuz referanslari mevcut mu.
"""

import gzip
import json
import re
import struct
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


def read_nbt(path):
    """Yapi sablonu NBT okuyucu (gzip'li, buyuk-endian)."""
    data = gzip.open(path, "rb").read()
    pos = [0]

    def u8():
        v = data[pos[0]]; pos[0] += 1; return v

    def rstr():
        n = struct.unpack_from(">H", data, pos[0])[0]; pos[0] += 2
        v = data[pos[0]:pos[0] + n].decode(); pos[0] += n; return v

    def payload(t):
        if t == 1: return u8()
        if t == 2:
            v = struct.unpack_from(">h", data, pos[0])[0]; pos[0] += 2; return v
        if t == 3:
            v = struct.unpack_from(">i", data, pos[0])[0]; pos[0] += 4; return v
        if t == 4:
            v = struct.unpack_from(">q", data, pos[0])[0]; pos[0] += 8; return v
        if t == 5:
            v = struct.unpack_from(">f", data, pos[0])[0]; pos[0] += 4; return v
        if t == 6:
            v = struct.unpack_from(">d", data, pos[0])[0]; pos[0] += 8; return v
        if t == 7:
            n = payload(3); pos[0] += n; return None
        if t == 8: return rstr()
        if t == 9:
            et = u8(); n = payload(3)
            return [payload(et) for _ in range(n)]
        if t == 10:
            d = {}
            while True:
                tt = u8()
                if tt == 0:
                    return d
                name = rstr(); d[name] = payload(tt)
        if t == 11:
            n = payload(3)
            v = [struct.unpack_from(">i", data, pos[0] + 4 * i)[0] for i in range(n)]
            pos[0] += 4 * n; return v
        if t == 12:
            n = payload(3); pos[0] += 8 * n; return None
        raise ValueError(f"bilinmeyen tag {t}")

    t = u8(); rstr()
    return payload(t)


def validate_villages(docs, online):
    nbt_root = RES / "data/realisticworld/structure"
    nbts = sorted(nbt_root.rglob("*.nbt")) if nbt_root.exists() else []
    jigsaw_pools = set()
    id_re = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_/.-]+$")
    for p in nbts:
        try:
            d = read_nbt(p)
        except Exception as e:
            err(f"{p.name}: NBT cozumlenemedi: {e}")
            continue
        if d.get("DataVersion") != 4903:
            err(f"{p.name}: DataVersion 4903 degil: {d.get('DataVersion')}")
        sx, sy, sz = d["size"]
        npal = len(d["palette"])
        entr = streets = 0
        for b in d["blocks"]:
            x, y, z = b["pos"]
            if not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz):
                err(f"{p.name}: blok sinir disi: {b['pos']}")
            if not (0 <= b["state"] < npal):
                err(f"{p.name}: palet indeksi gecersiz: {b['state']}")
            nbt = b.get("nbt")
            if nbt:
                jigsaw_pools.add(nbt["pool"])
                if nbt["name"] == "minecraft:building_entrance":
                    entr += 1
                if nbt["name"] == "minecraft:street":
                    streets += 1
        for pal in d["palette"]:
            if not id_re.match(pal["Name"]):
                err(f"{p.name}: gecersiz blok kimligi: {pal['Name']}")
        if p.stem == "plaza" and streets < 4:
            err(f"{p.name}: meydanin sokak cikisi yetersiz ({streets})")
        if p.stem in ("manor", "market", "cottage") and entr != 1:
            err(f"{p.name}: giris jigsaw sayisi 1 olmali ({entr})")
    print(f"{len(nbts)} NBT sablonu dogrulandi")

    # havuz location -> NBT dosyasi; yapi tanimi sinirlari
    for p, d in docs.items():
        sp = str(p)
        if "template_pool" in sp:
            for e in d.get("elements", []):
                loc = e["element"].get("location", "")
                if loc.startswith("realisticworld:"):
                    f = nbt_root / (loc.split(":", 1)[1] + ".nbt")
                    if not f.exists():
                        err(f"{p.name}: eksik NBT: {loc}")
        elif "worldgen/structure" in sp and p.suffix == ".json":
            if not (0 <= d["size"] <= 7):
                err(f"{p.name}: size codec siniri disinda (0..7): {d['size']}")
            # Codec: max_distance_from_center + arazi uyarlama payi <= 128.
            # Pay: none=0, bury/beard_thin/beard_box/encapsulate=12.
            blur = 0 if d.get("terrain_adaptation", "none") == "none" else 12
            mdc = d["max_distance_from_center"]
            if not (1 <= mdc <= 128):
                err(f"{p.name}: max_distance_from_center 1..128 disi: {mdc}")
            if mdc + blur > 128:
                err(f"{p.name}: max_distance_from_center + arazi payi ({blur}) "
                    f"128'i asiyor: {mdc}+{blur}")
            sp_pool = d["start_pool"]
            if sp_pool.startswith("realisticworld:"):
                f = RES / "data/realisticworld/worldgen/template_pool" / \
                    (sp_pool.split(":", 1)[1] + ".json")
                if not f.exists():
                    err(f"{p.name}: start_pool bulunamadi: {sp_pool}")

    # NBT jigsaw'larinin referans verdigi vanilla havuzlar
    for pool in sorted(jigsaw_pools):
        ns, path = pool.split(":", 1)
        if ns == "realisticworld":
            f = RES / "data/realisticworld/worldgen/template_pool" / (path + ".json")
            if not f.exists():
                err(f"eksik mod havuzu: {pool}")
        elif ns == "minecraft" and online:
            if not http_exists(f"{MCMETA}/template_pool/{path}.json"):
                err(f"vanilla'da yok: template_pool {pool}")
    print(f"{len(jigsaw_pools)} jigsaw havuz referansi kontrol edildi")


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

    # 2. referans butunlugu (noise/density function dosyalari;
    #    template_pool ve structure ayrica 5. adimda ele alinir)
    df_refs, noise_refs = set(), set()
    for p, d in docs.items():
        sp = str(p)
        if ("worldgen" in sp and p.suffix == ".json"
                and "world_preset" not in sp
                and "template_pool" not in sp
                and "worldgen/structure" not in sp):
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

    # 5. koy dosyalari
    validate_villages(docs, online)

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
