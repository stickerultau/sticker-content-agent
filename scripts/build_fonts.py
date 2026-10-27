"""Builds the static brand fonts in assets/fonts from the variable Google Fonts in assets/fonts/src.

Run once (the output is committed):  python scripts/build_fonts.py

Both fonts are SIL Open Font License (see assets/fonts/OFL-*.txt). Each static instance gets a
unique family name so Pillow and FFmpeg/libass pick exactly the same face.
"""
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
SRC = FONTS / "src"

INSTANCES = [
    # (source file, axes, output file, family name)
    ("BricolageGrotesque-VF.ttf", {"wght": 800, "opsz": 96, "wdth": 100}, "BrandDisplay.ttf", "Brand Display"),
    ("BricolageGrotesque-VF.ttf", {"wght": 600, "opsz": 36, "wdth": 100}, "BrandDisplaySemi.ttf", "Brand Display Semi"),
    ("Inter-VF.ttf", {"wght": 500, "opsz": 24}, "BrandBody.ttf", "Brand Body"),
    ("Inter-VF.ttf", {"wght": 700, "opsz": 28}, "BrandBodyBold.ttf", "Brand Body Bold"),
    ("Inter-VF.ttf", {"wght": 900, "opsz": 32}, "BrandCaption.ttf", "Brand Caption"),
]

# Characters the templates must render: Romanian diacritics (comma-below and cedilla forms) and arrows.
REQUIRED = "ăâîșțĂÂÎȘȚşţŞŢ→↓•–—“”„"


def rename(font: TTFont, family: str) -> None:
    name = font["name"]
    postscript = family.replace(" ", "") + "-Regular"
    for record in list(name.names):
        if record.nameID in (16, 17, 21, 22, 25):
            name.removeNames(nameID=record.nameID)
    for name_id, value in ((1, family), (2, "Regular"), (3, postscript), (4, family), (6, postscript)):
        name.setName(value, name_id, 3, 1, 0x409)
        name.setName(value, name_id, 1, 0, 0)
    font["OS/2"].usWeightClass = 400
    font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~0b1100001) | 0b1000000  # REGULAR bit only
    font["head"].macStyle = 0


def main() -> None:
    for src, axes, out, family in INSTANCES:
        font = TTFont(SRC / src)
        static = instantiateVariableFont(font, axes)
        rename(static, family)
        static.save(FONTS / out)
        cmap = static.getBestCmap()
        missing = [c for c in REQUIRED if ord(c) not in cmap]
        print(f"{out:24} {family:20} missing: {''.join(missing) or 'none'}")


if __name__ == "__main__":
    main()
