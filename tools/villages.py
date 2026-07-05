#!/usr/bin/env python3
"""Buyuk Koy Guncellemesi ureteci.

Vanilla 26.2 koy jigsaw sistemini genisletir:

  YAPI TANIMLARI (data/minecraft/worldgen/structure/village_*.json uzerine)
  - size 6 -> 7 (jigsaw derinlik ust siniri) ve max_distance_from_center
    80 -> 128: koyler cok daha genis alana yayilir.
  - start_pool -> realisticworld:village/<biyom>/town_centers: koyler artik
    planli buyuk meydandan baslar.

  MERKEZ MEYDAN (her biyom icin ozel NBT)
  - 15x15 tas doseli meydan: merkezi cesme, koy cani, pazar tezgahlari,
    fener direkleri, banklar ve cicek tarhlari.
  - 8 sokak cikisi (her kenarda 2): vanilla merkezlerdeki 3-4 cikisa karsilik
    koy her yone dogal bicimde dallanir.
  - Vanilla cesme/bulusma noktalari havuzda dusuk agirlikla korunur,
    zombi koyu varyantlari aynen kalir.

  OZEL BINALAR (havuzlara vanilla evlerin YANINA eklenir)
  - Konak: iki katli, 4 yatakli, kitaplikli buyuk ev (2 koylu).
  - Pazar: yun tenteli tezgahlarla acik carsi (2 koylu).
  - Kulube: bahceli, kompostorlu tas temelli ev (1 koylu).
  Biyoma gore malzeme paleti degisir (mese/akasya/ladin/kumtasi).

Jigsaw baglanti kurallari vanilla 26.2 NBT'lerinden cikarilmistir:
  - sokak cikisi: y=1, yatay yon, name/target=minecraft:street,
    joint=aligned, final_state=structure_void
  - ev girisi: y=0, disa bakan yon, name/target=minecraft:building_entrance,
    joint=aligned, final_state=basamak (esik)
  - koylu/golem/kedi: y=0, up_north, name/target=minecraft:bottom,
    joint=rollable, final_state=zemin blogu

Kullanim: python3 tools/villages.py [--ref-dir DIR] [--fetch]
"""

import argparse
import gzip
import io
import json
import struct
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "src/main/resources"
MCMETA = "https://raw.githubusercontent.com/misode/mcmeta/26.2-data/data/minecraft"
DATA_VERSION = 4903  # Minecraft 26.2
BIOMES = ["plains", "desert", "savanna", "snowy", "taiga"]

# ------------------------------------------------------------------ NBT yazma

def _tag(out, tagtype, name):
    out.write(struct.pack(">B", tagtype))
    b = name.encode()
    out.write(struct.pack(">H", len(b)) + b)


def _string(out, s):
    b = s.encode()
    out.write(struct.pack(">H", len(b)) + b)


def _compound(out, d):
    for k, v in d.items():
        if isinstance(v, str):
            _tag(out, 8, k); _string(out, v)
        elif isinstance(v, int):
            _tag(out, 3, k); out.write(struct.pack(">i", v))
        elif isinstance(v, dict):
            _tag(out, 10, k); _compound(out, v)
        else:
            raise TypeError(f"{k}: {type(v)}")
    out.write(b"\x00")


def write_structure_nbt(path, size, palette, blocks):
    """Yapi sablonu NBT dosyasi yazar.

    palette: [(name, props_dict|None), ...]
    blocks:  [(x, y, z, state_index, nbt_dict|None), ...]
    """
    out = io.BytesIO()
    _tag(out, 10, "")                                   # kok compound
    _tag(out, 9, "size"); out.write(struct.pack(">Bi", 3, 3))
    out.write(struct.pack(">iii", *size))
    _tag(out, 9, "entities"); out.write(struct.pack(">Bi", 0, 0))
    _tag(out, 9, "blocks"); out.write(struct.pack(">Bi", 10, len(blocks)))
    for x, y, z, state, nbt in blocks:
        _tag(out, 9, "pos"); out.write(struct.pack(">Bi", 3, 3))
        out.write(struct.pack(">iii", x, y, z))
        _tag(out, 3, "state"); out.write(struct.pack(">i", state))
        if nbt is not None:
            _tag(out, 10, "nbt"); _compound(out, nbt)
        out.write(b"\x00")
    _tag(out, 9, "palette"); out.write(struct.pack(">Bi", 10, len(palette)))
    for name, props in palette:
        if props:
            _tag(out, 10, "Properties"); _compound(out, props)
        _tag(out, 8, "Name"); _string(out, name)
        out.write(b"\x00")
    _tag(out, 3, "DataVersion"); out.write(struct.pack(">i", DATA_VERSION))
    out.write(b"\x00")                                  # kok compound sonu
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as f:
        f.write(out.getvalue())


# ------------------------------------------------------------ yapi kurucusu

def parse_state(state):
    """'minecraft:oak_stairs[facing=east,half=bottom]' -> (isim, ozellikler)"""
    if "[" in state:
        name, rest = state.split("[", 1)
        props = dict(p.split("=", 1) for p in rest.rstrip("]").split(","))
        return name, props
    return state, None


class Structure:
    """structure_void varsayilanli sablon; air acikca yerlestirilir.

    single_pool_element kullanildigi icin: air ic mekanlari gercekten bosaltir,
    structure_void hucreleri araziye dokunmaz.
    """

    def __init__(self, sx, sy, sz):
        self.size = (sx, sy, sz)
        self.palette = []
        self.index = {}
        self.cells = {}          # (x,y,z) -> (state_idx, nbt|None)

    def _state(self, state):
        name, props = parse_state(state)
        key = (name, tuple(sorted((props or {}).items())))
        if key not in self.index:
            self.index[key] = len(self.palette)
            self.palette.append((name, props))
        return self.index[key]

    def set(self, x, y, z, state, nbt=None):
        sx, sy, sz = self.size
        assert 0 <= x < sx and 0 <= y < sy and 0 <= z < sz, (x, y, z, self.size)
        self.cells[(x, y, z)] = (self._state(state), nbt)

    def fill(self, x1, y1, z1, x2, y2, z2, state):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                for z in range(min(z1, z2), max(z1, z2) + 1):
                    self.set(x, y, z, state)

    def jigsaw(self, x, y, z, orientation, pool, name, target, final, joint):
        self.set(x, y, z, f"minecraft:jigsaw[orientation={orientation}]", {
            "id": "minecraft:jigsaw", "pool": pool, "name": name,
            "target": target, "final_state": final, "joint": joint,
        })

    def save(self, path):
        void = self._state("minecraft:structure_void")
        blocks = []
        sx, sy, sz = self.size
        for y in range(sy):
            for z in range(sz):
                for x in range(sx):
                    state, nbt = self.cells.get((x, y, z), (void, None))
                    blocks.append((x, y, z, state, nbt))
        write_structure_nbt(path, self.size, self.palette, blocks)


# ----------------------------------------------------------- biyom paletleri

PAL = {
    "plains": dict(plank="minecraft:oak_planks", log="minecraft:oak_log[axis=y]",
                   stairs="minecraft:oak_stairs", slab="minecraft:oak_slab",
                   fence="minecraft:oak_fence", door="minecraft:oak_door",
                   base="minecraft:cobblestone", pave="minecraft:stone_bricks",
                   pave2="minecraft:cobblestone", ground="minecraft:grass_block",
                   window="minecraft:glass", flat_roof=False,
                   flower="minecraft:poppy"),
    "desert": dict(plank="minecraft:smooth_sandstone", log="minecraft:cut_sandstone",
                   stairs="minecraft:sandstone_stairs", slab="minecraft:smooth_sandstone_slab",
                   fence="minecraft:jungle_fence", door="minecraft:jungle_door",
                   base="minecraft:sandstone", pave="minecraft:smooth_sandstone",
                   pave2="minecraft:sandstone", ground="minecraft:sand",
                   window="minecraft:air", flat_roof=True,
                   flower="minecraft:dead_bush"),
    "savanna": dict(plank="minecraft:acacia_planks", log="minecraft:acacia_log[axis=y]",
                    stairs="minecraft:acacia_stairs", slab="minecraft:acacia_slab",
                    fence="minecraft:acacia_fence", door="minecraft:acacia_door",
                    base="minecraft:cobblestone", pave="minecraft:cobblestone",
                    pave2="minecraft:packed_mud", ground="minecraft:grass_block",
                    window="minecraft:glass", flat_roof=False,
                    flower="minecraft:dandelion"),
    "snowy": dict(plank="minecraft:spruce_planks", log="minecraft:stripped_spruce_log[axis=y]",
                  stairs="minecraft:spruce_stairs", slab="minecraft:spruce_slab",
                  fence="minecraft:spruce_fence", door="minecraft:spruce_door",
                  base="minecraft:cobblestone", pave="minecraft:cobblestone",
                  pave2="minecraft:snow_block", ground="minecraft:snow_block",
                  window="minecraft:glass", flat_roof=False,
                  flower="minecraft:lantern[hanging=false]"),
    "taiga": dict(plank="minecraft:spruce_planks", log="minecraft:spruce_log[axis=y]",
                  stairs="minecraft:spruce_stairs", slab="minecraft:spruce_slab",
                  fence="minecraft:spruce_fence", door="minecraft:spruce_door",
                  base="minecraft:cobblestone", pave="minecraft:cobblestone",
                  pave2="minecraft:mossy_cobblestone", ground="minecraft:grass_block",
                  window="minecraft:glass", flat_roof=False,
                  flower="minecraft:fern"),
}

WOOL = ["minecraft:white_wool", "minecraft:yellow_wool", "minecraft:lime_wool",
        "minecraft:light_blue_wool"]


def villagers_pool(biome):
    return f"minecraft:village/{biome}/villagers"


def ground_path(biome):
    return "minecraft:sand" if biome == "desert" else "minecraft:dirt_path"


# ------------------------------------------------------- ortak bina parcalari

def shell(s, p, x1, z1, x2, z2, floor_y, wall_y1, wall_y2):
    """Dikdortgen kat: zemin plaka + duvarlar + kose direkleri + ic hacim air."""
    s.fill(x1, floor_y, z1, x2, floor_y, z2, p["plank"])
    for y in range(wall_y1, wall_y2 + 1):
        for x in range(x1, x2 + 1):
            s.set(x, y, z1, p["plank"]); s.set(x, y, z2, p["plank"])
        for z in range(z1, z2 + 1):
            s.set(x1, y, z, p["plank"]); s.set(x2, y, z, p["plank"])
    for cx, cz in [(x1, z1), (x1, z2), (x2, z1), (x2, z2)]:
        for y in range(wall_y1, wall_y2 + 1):
            s.set(cx, y, cz, p["log"])
    s.fill(x1 + 1, wall_y1, z1 + 1, x2 - 1, wall_y2, z2 - 1, "minecraft:air")


def gable_roof(s, p, x1, x2, roof_z1, roof_z2, wall_z1, wall_z2, base_y):
    """x boyunca daralan, z boyunca uzanan besik cati; desert'te duz cati."""
    if p["flat_roof"]:
        s.fill(x1, base_y, roof_z1, x2, base_y, roof_z2, p["slab"])
        return
    width = x2 - x1 + 1
    steps = (width + 1) // 2
    for i in range(steps):
        y = base_y + i
        for z in range(roof_z1, roof_z2 + 1):
            s.set(x1 + i, y, z, f"{p['stairs']}[facing=east,half=bottom]")
            s.set(x2 - i, y, z, f"{p['stairs']}[facing=west,half=bottom]")
    if width % 2 == 1:  # tepe siras: tek genislikte slab sirti
        y = base_y + steps - 1
        for z in range(roof_z1, roof_z2 + 1):
            s.set(x1 + steps - 1, y, z, p["slab"])
    # alinlik ucgenleri (bina duvar duzlemlerinde)
    for i in range(1, steps):
        lo, hi = x1 + i, x2 - i
        if lo > hi:
            break
        for x in range(lo, hi + 1):
            s.set(x, base_y + i - 1, wall_z1, p["plank"])
            s.set(x, base_y + i - 1, wall_z2, p["plank"])


def entrance(s, p, biome, wall_x, z_door):
    """Bati yonune (x=0'a dogru) kapi + vanilla kurali giris jigsaw'i."""
    s.jigsaw(wall_x - 1, 0, z_door, "west_up",
             f"minecraft:village/{biome}/streets",
             "minecraft:building_entrance", "minecraft:building_entrance",
             f"{p['stairs']}[facing=east,half=bottom]", "aligned")
    d = p["door"]
    s.set(wall_x, 1, z_door,
          f"{d}[half=lower,facing=east,hinge=left,open=false,powered=false]")
    s.set(wall_x, 2, z_door,
          f"{d}[half=upper,facing=east,hinge=left,open=false,powered=false]")


def bed(s, x, y, z, color):
    """Basi kuzeye (z-1) bakan yatak."""
    s.set(x, y, z, f"minecraft:{color}_bed[part=foot,facing=north,occupied=false]")
    s.set(x, y, z - 1, f"minecraft:{color}_bed[part=head,facing=north,occupied=false]")


def villager(s, biome, x, z, floor_state):
    s.jigsaw(x, 0, z, "up_north", villagers_pool(biome),
             "minecraft:bottom", "minecraft:bottom", floor_state, "rollable")


# ------------------------------------------------------------------- meydan

def build_plaza(biome):
    """15x15 planli koy meydani: cesme, can, tezgahlar, 8 sokak cikisi."""
    p = PAL[biome]
    s = Structure(15, 6, 15)
    # zemin: kenar serit dogal zemin, ici satranc desenli doseme
    for x in range(15):
        for z in range(15):
            if x in (0, 14) or z in (0, 14):
                s.set(x, 0, z, p["ground"])
            else:
                s.set(x, 0, z, p["pave"] if (x + z) % 2 == 0 else p["pave2"])
    # meydan ustunu temizle (air gercekten yerlestirilir -> otlar/kum temizlenir)
    s.fill(0, 1, 0, 14, 1, 14, "minecraft:air")
    s.fill(1, 2, 1, 13, 4, 13, "minecraft:air")

    # merkezi cesme (5x5, merkez 7,7)
    for x in range(5, 10):
        for z in range(5, 10):
            corner = x in (5, 9) and z in (5, 9)
            edge = x in (5, 9) or z in (5, 9)
            if corner:
                s.set(x, 1, z, "minecraft:stone_brick_wall[up=true,north=none,south=none,east=none,west=none,waterlogged=false]"
                      if not p["flat_roof"] else p["base"])
            elif edge:
                s.set(x, 1, z, "minecraft:stone_bricks" if not p["flat_roof"] else p["base"])
            else:
                s.set(x, 1, z, "minecraft:ice" if biome == "snowy"
                      else "minecraft:water[level=0]")
    s.set(7, 1, 7, p["base"]); s.set(7, 2, 7, p["base"])
    s.set(7, 3, 7, "minecraft:lantern[hanging=false]")

    # koy cani: kaide + can
    s.set(2, 1, 7, p["base"])
    s.set(2, 2, 7, "minecraft:bell[attachment=floor,facing=east,powered=false]")

    # fener direkleri (ic koseler)
    for x, z in [(2, 2), (2, 12), (12, 2), (12, 12)]:
        s.set(x, 1, z, "minecraft:cobblestone_wall[up=true,north=none,south=none,east=none,west=none,waterlogged=false]")
        s.set(x, 2, z, "minecraft:cobblestone_wall[up=true,north=none,south=none,east=none,west=none,waterlogged=false]")
        s.set(x, 3, z, "minecraft:lantern[hanging=false]")

    # iki pazar tezgahi (kuzey kenara yakin)
    for x0, wool in [(4, WOOL[1]), (9, WOOL[3])]:
        z0 = 2
        for dx in range(3):
            s.set(x0 + dx, 1, z0, "minecraft:barrel[facing=up,open=false]"
                  if dx == 1 else "minecraft:hay_block[axis=y]")
            s.set(x0 + dx, 3, z0, wool)
            s.set(x0 + dx, 3, z0 + 1, wool)
        for dx in (0, 2):
            s.set(x0 + dx, 1, z0 + 1, p["fence"])
            s.set(x0 + dx, 2, z0 + 1, p["fence"])

    # banklar (guneyde cesmeye bakan basamaklar)
    for x in range(5, 10):
        s.set(x, 1, 12, f"{p['stairs']}[facing=north,half=bottom]")

    # cicek tarhlari
    if biome not in ("desert", "snowy"):
        for x, z in [(4, 12), (10, 12)]:
            s.set(x, 1, z, p["flower"])

    # 8 sokak cikisi: her kenarda 2 (koordinat 3 ve 11), y=1
    street = f"minecraft:village/{biome}/streets"
    for c in (3, 11):
        s.jigsaw(c, 1, 0, "north_up", street, "minecraft:street",
                 "minecraft:street", "minecraft:structure_void", "aligned")
        s.jigsaw(c, 1, 14, "south_up", street, "minecraft:street",
                 "minecraft:street", "minecraft:structure_void", "aligned")
        s.jigsaw(0, 1, c, "west_up", street, "minecraft:street",
                 "minecraft:street", "minecraft:structure_void", "aligned")
        s.jigsaw(14, 1, c, "east_up", street, "minecraft:street",
                 "minecraft:street", "minecraft:structure_void", "aligned")

    # canlilar: demir golem, kediler, koyluler (y=0, zemin bloguna gomulu)
    path = ground_path(biome)
    s.jigsaw(7, 0, 12, "up_north", "minecraft:village/common/iron_golem",
             "minecraft:bottom", "minecraft:bottom", path, "rollable")
    s.jigsaw(3, 0, 7, "up_north", "minecraft:village/common/cats",
             "minecraft:bottom", "minecraft:bottom", path, "rollable")
    for x, z in [(11, 7), (7, 3), (11, 11)]:
        villager(s, biome, x, z, path)
    return s


# ------------------------------------------------------------------- binalar

def build_manor(biome):
    """Iki katli konak: 4 yatak, kitaplik, kursu, ic merdiven; 2 koylu."""
    p = PAL[biome]
    s = Structure(11, 14, 9)
    shell(s, p, 1, 1, 9, 7, 0, 1, 3)      # zemin kat (taban y0, duvar y1-3)
    shell(s, p, 1, 1, 9, 7, 4, 5, 7)      # ust kat (taban y4, duvar y5-7)
    entrance(s, p, biome, 1, 4)
    # pencereler (kuzey/guney duvarlar + bati/dogu)
    if p["window"] != "minecraft:air":
        for x in (3, 5, 7):
            for y in (2, 6):
                s.set(x, y, 1, p["window"]); s.set(x, y, 7, p["window"])
        for y in (2, 6):
            s.set(1, y, 2, p["window"]); s.set(1, y, 6, p["window"])
            s.set(9, y, 2, p["window"]); s.set(9, y, 6, p["window"])
    # ic merdiven (dogu duvari boyunca): y1..y4 basamaklari, tavan bosluklari
    for i in range(4):
        s.set(8 - i, 1 + i, 6, f"{p['stairs']}[facing=west,half=bottom]")
    for x in (8, 7, 6):
        s.set(x, 4, 6, "minecraft:air")   # ust kat tabaninda merdiven bosluğu
    # zemin kat esyalari
    s.set(2, 1, 2, "minecraft:bookshelf"); s.set(2, 2, 2, "minecraft:bookshelf")
    s.set(3, 1, 2, "minecraft:lectern[facing=south,has_book=false,powered=false]")
    s.set(8, 1, 2, "minecraft:crafting_table")
    s.set(2, 1, 6, "minecraft:barrel[facing=up,open=false]")
    bed(s, 5, 1, 3, "red")
    # ust kat: 3 yatak + hali
    bed(s, 3, 5, 3, "white"); bed(s, 5, 5, 3, "light_gray"); bed(s, 7, 5, 3, "blue")
    s.set(5, 5, 5, "minecraft:red_carpet")
    # cati (9 genislik, sacaksiz; alinlik z=1 ve z=7 duzlemlerinde)
    gable_roof(s, p, 1, 9, 0, 8, 1, 7, 8)
    # koyluler (zemin plakasina gomulu, final=plank)
    villager(s, biome, 4, 2, p["plank"])
    villager(s, biome, 6, 5, p["plank"])
    return s


def build_market(biome):
    """Acik carsi: yun tenteli 4 tezgah, kompostor; 2 koylu."""
    p = PAL[biome]
    s = Structure(13, 6, 9)
    for x in range(13):
        for z in range(9):
            s.set(x, 0, z, p["pave2"] if (x + z) % 3 else p["pave"])
    s.fill(0, 1, 0, 12, 4, 8, "minecraft:air")
    for i, x0 in enumerate((1, 7)):
        for j, z0 in enumerate((1, 5)):
            wool = WOOL[(i * 2 + j) % 4]
            for x in range(x0, x0 + 4):
                for z in range(z0, z0 + 3):
                    s.set(x, 3, z, wool)
            for cx, cz in [(x0, z0), (x0 + 3, z0), (x0, z0 + 2), (x0 + 3, z0 + 2)]:
                s.set(cx, 1, cz, p["fence"]); s.set(cx, 2, cz, p["fence"])
            s.set(x0 + 1, 1, z0 + 1, "minecraft:barrel[facing=up,open=false]")
            s.set(x0 + 2, 1, z0 + 1, "minecraft:hay_block[axis=y]")
    s.set(6, 1, 4, "minecraft:composter[level=0]")
    s.jigsaw(0, 0, 4, "west_up", f"minecraft:village/{biome}/streets",
             "minecraft:building_entrance", "minecraft:building_entrance",
             f"{p['stairs']}[facing=east,half=bottom]", "aligned")
    path = ground_path(biome)
    villager(s, biome, 6, 2, path)
    villager(s, biome, 6, 6, path)
    return s


def build_cottage(biome):
    """Bahceli kulube: yatak, kompostor, citli cicek bahcesi; 1 koylu."""
    p = PAL[biome]
    s = Structure(11, 9, 8)
    s.fill(1, 0, 1, 6, 0, 6, p["base"])            # tas temel plakasi
    shell(s, p, 1, 1, 6, 6, 0, 1, 3)
    s.fill(1, 0, 1, 6, 0, 6, p["base"])            # shell zeminini tasa cevir
    s.fill(2, 0, 2, 5, 0, 5, p["plank"])           # ic zemin ahsap
    entrance(s, p, biome, 1, 3)
    if p["window"] != "minecraft:air":
        s.set(3, 2, 1, p["window"]); s.set(4, 2, 6, p["window"])
        s.set(6, 2, 3, p["window"])
    bed(s, 4, 1, 4, "yellow")
    s.set(5, 1, 2, "minecraft:barrel[facing=up,open=false]")
    s.set(2, 1, 5, "minecraft:crafting_table")
    gable_roof(s, p, 0, 7, 0, 7, 1, 6, 4)
    # yan bahce (dogu): cit, kompostor, cicekler
    s.fill(8, 0, 1, 10, 0, 6, p["ground"])
    for z in range(1, 7):
        s.set(10, 1, z, p["fence"])
    for x in (8, 9):
        s.set(x, 1, 1, p["fence"]); s.set(x, 1, 6, p["fence"])
    s.set(8, 1, 2, "minecraft:composter[level=0]")
    if biome not in ("desert", "snowy"):
        s.set(9, 1, 3, p["flower"]); s.set(8, 1, 4, p["flower"])
    villager(s, biome, 3, 5, p["plank"])
    return s


# ----------------------------------------------------------- JSON uretimleri

def element(location, projection="rigid", processors=None):
    return {"element_type": "minecraft:single_pool_element",
            "location": location,
            "processors": processors or {"processors": []},
            "projection": projection}


def fetch_refs(ref_dir):
    for b in BIOMES:
        for rel in [f"worldgen/template_pool/village/{b}/town_centers.json",
                    f"worldgen/template_pool/village/{b}/houses.json",
                    f"worldgen/structure/village_{b}.json"]:
            dest = ref_dir / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            url = f"{MCMETA}/{rel}"
            print(f"  indiriliyor: {url}")
            with urllib.request.urlopen(url) as r:
                dest.write_bytes(r.read())


def dump_json(rel, obj):
    path = RES / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")
    print(f"  yazildi: {path.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-dir", type=Path, default=ROOT / ".cache/mcmeta-26.2")
    ap.add_argument("--fetch", action="store_true")
    args = ap.parse_args()
    if args.fetch:
        fetch_refs(args.ref_dir)

    for biome in BIOMES:
        # --- NBT sablonlari
        for name, builder in [("plaza", build_plaza), ("manor", build_manor),
                              ("market", build_market), ("cottage", build_cottage)]:
            st = builder(biome)
            st.save(RES / f"data/realisticworld/structure/village/{biome}/{name}.nbt")
        print(f"  {biome}: 4 NBT sablonu yazildi")

        # --- baslangic havuzu: buyuk meydan + vanilla merkezler (dusuk agirlik)
        vanilla_tc = json.loads((args.ref_dir /
            f"worldgen/template_pool/village/{biome}/town_centers.json").read_text())
        elements = [{"weight": 60, "element": element(
            f"realisticworld:village/{biome}/plaza")}]
        for e in vanilla_tc["elements"]:
            e = dict(e)
            e["weight"] = max(1, e["weight"] // 5)   # 50 -> 10, zombi 1 -> 1
            elements.append(e)
        dump_json("data/realisticworld/worldgen/template_pool/"
                  f"village/{biome}/town_centers.json",
                  {"fallback": vanilla_tc["fallback"], "elements": elements})

        # --- ev havuzu: vanilla evler + ozel binalar
        houses = json.loads((args.ref_dir /
            f"worldgen/template_pool/village/{biome}/houses.json").read_text())
        houses["elements"] = houses["elements"] + [
            {"weight": 4, "element": element(f"realisticworld:village/{biome}/manor")},
            {"weight": 4, "element": element(f"realisticworld:village/{biome}/market")},
            {"weight": 6, "element": element(f"realisticworld:village/{biome}/cottage")},
        ]
        dump_json(f"data/minecraft/worldgen/template_pool/village/{biome}/houses.json",
                  houses)

        # --- yapi tanimi: daha derin, daha genis, ozel merkezden baslayan
        struct_json = json.loads((args.ref_dir /
            f"worldgen/structure/village_{biome}.json").read_text())
        assert struct_json["size"] == 6 and \
            struct_json["max_distance_from_center"] == 80, \
            f"beklenmeyen vanilla degerleri: {biome}"
        struct_json["size"] = 7
        struct_json["max_distance_from_center"] = 128
        struct_json["start_pool"] = f"realisticworld:village/{biome}/town_centers"
        dump_json(f"data/minecraft/worldgen/structure/village_{biome}.json", struct_json)

    print("Koy guncellemesi tamamlandi.")


if __name__ == "__main__":
    main()
