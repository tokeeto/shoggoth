#!/usr/bin/env python3
"""Build the card-text editor fonts: a base text font plus AHLCGSymbol icon ligatures.

Each markup tag in `FONT_ICON_TAGS` (e.g. "<combat>", "[fast]") becomes a `calt` ligature
that swaps the whole run of ASCII characters for a single icon glyph. The characters stay
in the document, so the editor still edits them one at a time; only the drawing changes.

The base font is subset (no Nerd Font icons, no programming ligatures), its icon-free
`calt`/`ccmp`/... layout is dropped, and it's renamed so that the Regular and Italic
builds form ONE family ("Shoggoth Editor Maple"): `QFont.setItalic(True)` then picks the
italic build automatically.

Usage (from the repo root):

    uv run --with fonttools python scripts/build_editor_font.py \\
        --regular ../shoggoth_assets/fonts/Maple/MapleMono-NF-Light.ttf \\
        --italic  ../shoggoth_assets/fonts/Maple/MapleMono-NF-LightItalic.ttf

Output goes to ../shoggoth_assets/fonts/ (override with --out-dir).
"""

import argparse
import sys
from pathlib import Path

from fontTools import subset
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

DEFAULT_ASSETS = REPO.parent / "shoggoth_assets" / "fonts"
FAMILY = "Shoggoth Editor Maple"

# Icons were designed against a cap height of 662 (Arno Pro); scale them to the base
# font's cap height so they keep the same relationship to the letters around them.
ARNO_CAP_HEIGHT = 662

# Codepoint ranges kept from the base font: everything the shipped translations
# (de/en/es/fr/it/pl/pt/ru) plus common typography need. zh falls back to a system font.
UNICODE_RANGES = [
    (0x20, 0x7E), (0xA0, 0x24F),       # Basic Latin, Latin-1, Latin Extended-A/B
    (0x2B0, 0x2FF), (0x300, 0x36F),    # modifier letters, combining marks
    (0x370, 0x3FF), (0x400, 0x52F),    # Greek, Cyrillic
    (0x1E00, 0x1EFF),                  # Latin Extended Additional (Vietnamese etc.)
    (0x2000, 0x206F), (0x20A0, 0x20CF),  # general punctuation, currency
    (0x2100, 0x214F), (0x2190, 0x21FF),  # letterlike, arrows
    (0x2200, 0x22FF), (0x25A0, 0x25FF),  # math operators, geometric shapes
]

PUA_START = 0xE000  # icon glyphs are also reachable by codepoint, like the old font


def load_icon_tags():
    """Tag → symbol-font character, straight from the renderer so they can't drift."""
    from shoggoth.renderer.richtext.tags import FONT_ICON_TAGS
    return dict(FONT_ICON_TAGS)


def subset_base(font):
    options = subset.Options()
    options.layout_features = []         # drop Maple's programming ligatures / cv / ss
    options.layout_closure = False
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.notdef_outline = True
    options.glyph_names = True
    options.hinting = True               # keep Maple's small-size hinting
    options.drop_tables += ["GSUB", "GPOS"]
    unicodes = [cp for lo, hi in UNICODE_RANGES for cp in range(lo, hi + 1)]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(font)


def glyph_name_for_char(cmap, ch):
    return cmap[ord(ch)]


def add_icon_glyphs(font, symbol, symbol_chars, scale):
    """Copy `symbol_chars` (chars in AHLCGSymbol's cmap) into `font` as `icon_<char>` glyphs.

    AHLCGSymbol is CFF (cubic); the base is TrueType (quadratic), so outlines go through
    Cu2QuPen. Returns {char: glyph name}."""
    sym_cmap = symbol.getBestCmap()
    sym_set = symbol.getGlyphSet()
    glyf, hmtx = font["glyf"], font["hmtx"]
    order = list(font.getGlyphOrder())
    names = {}
    for ch in sorted(symbol_chars):
        src = sym_cmap[ord(ch)]
        name = f"icon_{src}"
        pen = TTGlyphPen(None)
        # CFF contours run opposite to TrueType's, hence reverse_direction.
        conv = Cu2QuPen(pen, max_err=1.0, reverse_direction=True)
        sym_set[src].draw(TransformPen(conv, (scale, 0, 0, scale, 0, 0)))
        glyph = pen.glyph()
        glyf.glyphs[name] = glyph
        order.append(name)
        glyph.recalcBounds(glyf)
        advance = round(symbol["hmtx"][src][0] * scale)
        hmtx.metrics[name] = (advance, getattr(glyph, "xMin", 0))
        names[ch] = name
    font.setGlyphOrder(order)
    glyf.glyphOrder = order
    return names


def add_pua_cmap(font, names):
    for i, name in enumerate(sorted(names.values())):
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[PUA_START + i] = name


def build_features(font, tag_to_char, icon_names):
    cmap = font.getBestCmap()
    rules = []
    for tag, ch in sorted(tag_to_char.items()):
        seq = " ".join(glyph_name_for_char(cmap, c) for c in tag)
        rules.append(f"    sub {seq} by {icon_names[ch]};")
    icons = " ".join(sorted(set(icon_names.values())))
    fea = (
        "languagesystem DFLT dflt;\n"
        "languagesystem latn dflt;\n"
        "languagesystem cyrl dflt;\n"
        "languagesystem grek dflt;\n"
        "feature calt {\n" + "\n".join(rules) + "\n} calt;\n"
        f"table GDEF {{ GlyphClassDef , [{icons}], , ; }} GDEF;\n"
    )
    addOpenTypeFeaturesFromString(font, fea)


def rename(font, style):
    italic = style == "Italic"
    name = font["name"]
    name.names = [n for n in name.names if n.nameID not in (16, 17, 21, 22, 25)]
    full = f"{FAMILY} {style}".replace(" Regular", "")
    ps = f"{FAMILY.replace(' ', '')}-{style}"
    for nid, value in ((1, FAMILY), (2, style), (3, f"{ps};shoggoth"), (4, f"{FAMILY} {style}"), (6, ps)):
        for pid, eid, lid in ((3, 1, 0x409), (1, 0, 0)):
            name.setName(value, nid, pid, eid, lid)
    os2 = font["OS/2"]
    os2.usWeightClass = 400   # Light is the "Regular" of this family
    os2.fsSelection = (os2.fsSelection & ~0b1100001) | (0b1 if italic else 0b1000000)
    font["head"].macStyle = 0b10 if italic else 0
    return full


def build(base_path, symbol, tag_to_char, style, out_dir):
    font = TTFont(base_path)
    subset_base(font)
    cap = font["OS/2"].sCapHeight
    scale = cap / ARNO_CAP_HEIGHT
    icon_names = add_icon_glyphs(font, symbol, set(tag_to_char.values()), scale)
    add_pua_cmap(font, icon_names)
    build_features(font, tag_to_char, icon_names)
    rename(font, style)
    out = out_dir / f"ShoggothEditorMaple-{style}.ttf"
    font.save(out)
    print(f"{out.name}: {len(font.getGlyphOrder())} glyphs, {out.stat().st_size // 1024} KB, "
          f"icon scale {scale:.3f}, {len(tag_to_char)} tags")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regular", type=Path, required=True)
    ap.add_argument("--italic", type=Path, required=True)
    ap.add_argument("--symbol", type=Path, default=DEFAULT_ASSETS / "AHLCGSymbol.otf")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_ASSETS)
    args = ap.parse_args()

    symbol = TTFont(args.symbol)
    tags = load_icon_tags()
    missing = {ch for ch in tags.values() if ord(ch) not in symbol.getBestCmap()}
    if missing:
        sys.exit(f"symbol font lacks glyphs for: {sorted(missing)}")
    for path, style in ((args.regular, "Regular"), (args.italic, "Italic")):
        build(path, symbol, tags, style, args.out_dir)


if __name__ == "__main__":
    main()
