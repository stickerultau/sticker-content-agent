"""Step 4a — Design: brand templates for carousel slides, reel overlays and covers.

Every post goes through the same templates, so the page looks like one brand even though the artwork changes daily.
"""
from __future__ import annotations

import re
from functools import lru_cache
from itertools import combinations

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from .settings import FONTS

W, H = 1080, 1350        # carousel slide (4:5)
RW, RH = 1080, 1920      # reel frame (9:16)
M = 72                   # outer margin
CAPTION_YELLOW = "#FFD84D"

_CEDILLA = str.maketrans("şţŞŢ", "șțȘȚ")


def fix_ro(text: str) -> str:
    return text.translate(_CEDILLA)


@lru_cache(maxsize=None)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"{name}.ttf"), size)


def rgb(hex_color: str, alpha: int | None = None):
    h = hex_color.lstrip("#")
    value = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return value if alpha is None else (*value, alpha)


# ---------------------------------------------------------------------------------------------- surfaces

def background(size: tuple[int, int], color: str, glow: int = 70) -> Image.Image:
    """Flat brand color with a soft top-left light and fine paper grain."""
    img = Image.new("RGB", size, rgb(color))
    w, h = size
    radial = Image.radial_gradient("L").resize((int(w * 2.2), int(h * 2.2)))
    radial = ImageOps.invert(radial).crop((int(w * 0.55), int(h * 0.65), int(w * 0.55) + w, int(h * 0.65) + h))
    light = Image.new("RGB", size, (255, 255, 255))
    img = Image.composite(light, img, radial.point(lambda v: v * glow // 255))
    return grain(img)


def grain(img: Image.Image, strength: float = 0.5) -> Image.Image:
    noise = Image.effect_noise(img.size, 22).convert("RGB")
    textured = ImageChops.soft_light(img, noise)
    return Image.blend(img, textured, strength)


def cover_fit(img: Image.Image, size: tuple[int, int], zoom: float = 1.0) -> Image.Image:
    img = img.convert("RGB")
    if zoom > 1:
        w, h = img.size
        cw, ch = int(w / zoom), int(h / zoom)
        img = img.crop(((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2))
    return ImageOps.fit(img, size, Image.LANCZOS)


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    return mask


def card(image: Image.Image, size: tuple[int, int], radius: int = 30, border: int = 12, zoom: float = 1.3) -> Image.Image:
    """A photo-print style card: white rounded frame around a crop of the image."""
    w, h = size
    tile = Image.new("RGBA", size, (255, 255, 255, 255))
    inner = (w - 2 * border, h - 2 * border)
    photo = cover_fit(image, inner, zoom).convert("RGBA")
    tile.paste(photo, (border, border), rounded_mask(inner, max(radius - border, 6)))
    tile.putalpha(rounded_mask(size, radius))
    return tile


def place(canvas: Image.Image, layer: Image.Image, center: tuple[int, int], angle: float = 0,
          shadow: int = 90, blur: int = 26, drop: int = 18) -> None:
    """Alpha-composites `layer` rotated around `center`, with a soft drop shadow."""
    if angle:
        layer = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
    x, y = center[0] - layer.width // 2, center[1] - layer.height // 2
    if shadow:
        pad = blur * 3
        sh = Image.new("RGBA", (layer.width + 2 * pad, layer.height + 2 * pad), (0, 0, 0, 0))
        alpha = layer.getchannel("A").point(lambda v: v * shadow // 255)
        sh.paste((20, 16, 40, 255), (pad, pad), alpha)
        sh = sh.filter(ImageFilter.GaussianBlur(blur))
        canvas.alpha_composite(sh, (x - pad, y - pad + drop))
    canvas.alpha_composite(layer, (x, y))


# ---------------------------------------------------------------------------------------------- type

def wrap(words: list[str], fnt: ImageFont.FreeTypeFont, max_w: float, extra: float = 0) -> list[list[str]]:
    lines, line = [], []
    for word in words:
        trial = line + [word]
        if line and fnt.getlength(" ".join(trial)) + extra * len(trial) > max_w:
            lines.append(line)
            line = [word]
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def balanced(words: list[str], fnt: ImageFont.FreeTypeFont, count: int) -> list[str]:
    """Splits words into `count` lines of similar width (no lonely last word)."""
    if count < 2 or len(words) > 14:
        return []
    best = None
    for cuts in combinations(range(1, len(words)), count - 1):
        bounds = (0, *cuts, len(words))
        lines = [" ".join(words[a:b]) for a, b in zip(bounds, bounds[1:])]
        widest = max(fnt.getlength(line) for line in lines)
        if best is None or widest < best[0]:
            best = (widest, lines)
    return best[1] if best else []


def fit(text: str, name: str, max_w: float, max_lines: int, sizes: range) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    words = fix_ro(text).split()
    for size in sizes:
        fnt = font(name, size)
        lines = wrap(words, fnt, max_w)
        if len(lines) <= max_lines:
            return fnt, balanced(words, fnt, len(lines)) or [" ".join(line) for line in lines]
    fnt = font(name, sizes[-1])
    return fnt, [" ".join(line) for line in wrap(words, fnt, max_w)][:max_lines]


def tracked(draw: ImageDraw.ImageDraw, xy, text: str, fnt, fill, tracking: float) -> float:
    """Draws letter-spaced text (left-baseline anchored); returns its width."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill, anchor="ls")
        x += fnt.getlength(ch) + tracking
    return x - xy[0] - tracking


def pill(canvas: Image.Image, xy, text: str, fnt, fill, color, pad_x: int = 24, height: int = 54,
         tracking: float = 0, anchor: str = "left", pad_left: int | None = None) -> tuple[int, int, int, int]:
    draw = ImageDraw.Draw(canvas)
    pad_left = pad_x if pad_left is None else pad_left
    width = sum(fnt.getlength(c) + tracking for c in text) - tracking if tracking else fnt.getlength(text)
    total = int(width + pad_left + pad_x)
    x, y = xy
    if anchor == "right":
        x -= total
    elif anchor == "center":
        x -= total // 2
    box = (x, y, x + total, y + height)
    draw.rounded_rectangle(box, height // 2, fill=fill)
    ascent, descent = fnt.getmetrics()
    baseline = y + height / 2 + (ascent - descent) / 2 - 1
    if tracking:
        tracked(draw, (x + pad_left, baseline), text, fnt, color, tracking)
    else:
        draw.text((x + pad_left, baseline), text, font=fnt, fill=color, anchor="ls")
    return box


def marked_words(text: str) -> list[tuple[str, bool]]:
    """'5 stickere *spooky* pentru laptop' -> [('5', False), ..., ('spooky', True), ...]"""
    result, highlighted = [], False
    for token in fix_ro(text).split():
        start = token.startswith("*")
        end = token.endswith("*") and (len(token) > 1 or not start)
        word = token.strip("*")
        if start:
            highlighted = True
        if word:
            result.append((word, highlighted))
        if end:
            highlighted = False
    return result


def headline(canvas: Image.Image, text: str, x: int, y: int, max_w: int, ink: str, accent: str,
             max_lines: int = 3, sizes: range = range(116, 63, -4), align: str = "left") -> int:
    """Big display headline; *marked* words become tilted sticker labels. Returns the bottom y."""
    words = marked_words(text)
    for size in sizes:
        fnt = font("BrandDisplay", size)
        pad = size * 0.2
        lines, line, width = [], [], 0.0
        for word, hl in words:
            ww = fnt.getlength(word) + (2 * pad if hl else 0)
            space = fnt.getlength(" ") if line else 0
            if line and width + space + ww > max_w:
                lines.append(line)
                line, width = [], 0.0
                space = 0
            line.append((word, hl, ww))
            width += space + ww
        if line:
            lines.append(line)
        if len(lines) <= max_lines:
            break
    draw = ImageDraw.Draw(canvas)
    ascent, _ = fnt.getmetrics()
    leading = int(size * 1.04)
    baseline = y + ascent
    for line in lines:
        line_w = sum(ww for _, _, ww in line) + fnt.getlength(" ") * (len(line) - 1)
        cx = x + (max_w - line_w) / 2 if align == "center" else x
        for word, hl, ww in line:
            if hl:
                label = sticker_label(word, fnt, accent, "#FFFFFF", pad=int(pad))
                place(canvas, label, (int(cx + ww / 2), int(baseline - size * 0.33)), angle=-3, shadow=60, blur=10, drop=6)
            else:
                draw.text((cx, baseline), word, font=fnt, fill=rgb(ink), anchor="ls")
            cx += ww + fnt.getlength(" ")
        baseline += leading
    return int(baseline - leading + size * 0.28)


def sticker_label(text: str, fnt, fill: str, color: str, pad: int = 20) -> Image.Image:
    """A word on a rounded label with a white die-cut edge: looks like a sticker slapped on."""
    ascent, descent = fnt.getmetrics()
    w = int(fnt.getlength(text) + 2 * pad)
    h = int(fnt.size * 0.98 + pad * 0.9)
    edge = max(5, fnt.size // 16)
    tile = Image.new("RGBA", (w + 2 * edge, h + 2 * edge), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle((0, 0, tile.width - 1, tile.height - 1), radius=h // 3 + edge, fill=(255, 255, 255, 255))
    d.rounded_rectangle((edge, edge, edge + w - 1, edge + h - 1), radius=h // 3, fill=rgb(fill, 255))
    baseline = edge + h / 2 + (ascent - descent) / 2 - fnt.size * 0.02
    d.text((edge + pad, baseline), text, font=fnt, fill=rgb(color), anchor="ls")
    return tile


# ---------------------------------------------------------------------------------------------- carousel

def fan(canvas: Image.Image, images: list[Image.Image], top: int, bottom: int, card_w: int = 340) -> None:
    """Fanned, overlapping cards like a hand of playing cards; the middle one on top.
    The whole fan (including the lower outer cards) is centered between `top` and `bottom`."""
    n = len(images)
    card_h = int(card_w * 1.25)
    cy = (top + bottom) // 2 - 40
    order = sorted(range(n), key=lambda i: -abs(i - (n - 1) / 2))
    for i in order:
        t = (i - (n - 1) / 2) / max((n - 1) / 2, 1)          # -1 .. 1
        cx = int(W / 2 + t * (W / 2 - card_w / 2 - 28))
        y = int(cy + 70 * t * t)
        place(canvas, card(images[i], (card_w, card_h)), (cx, y), angle=-13 * t)


def carousel_cover(copy: dict, images: list[Image.Image], palette: dict, brand: dict, page: dict) -> Image.Image:
    ink, accent = brand["ink"], palette["accent"]
    canvas = background((W, H), palette["bg"]).convert("RGBA")
    pill(canvas, (M, 70), fix_ro(copy["kicker"]).upper(), font("BrandBodyBold", 25), rgb(ink), rgb(palette["bg"]),
         height=52, tracking=2.5)
    bottom = headline(canvas, copy["title"], M, 156, W - 2 * M, ink, accent)
    fan(canvas, images, bottom, H - 110)
    draw = ImageDraw.Draw(canvas)
    draw.text((M, H - 62), "@" + page["handle"], font=font("BrandBodyBold", 30), fill=rgb(ink), anchor="ls")
    pill(canvas, (W - M, H - 100), "Glisează  →", font("BrandBodyBold", 26), (255, 255, 255), rgb(ink),
         height=56, anchor="right")
    return canvas.convert("RGB")


def carousel_item(item: dict, index: int, total: int, image: Image.Image, palette: dict, brand: dict,
                  page: dict) -> Image.Image:
    ink = brand["ink"]
    canvas = cover_fit(image, (W, H)).convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    number_font = font("BrandDisplay", 150)
    number = f"{index:02d}"
    draw.text((M - 8, 190), number, font=number_font, fill=rgb(ink), anchor="ls")
    draw.text((M + number_font.getlength(number) + 4, 98), f"/{total:02d}", font=font("BrandBodyBold", 30),
              fill=rgb(ink, 150), anchor="ls")
    draw.text((W - M, 100), "@" + page["handle"], font=font("BrandBodyBold", 26), fill=rgb(ink, 150), anchor="rs")

    # Frosted info card at the bottom.
    inner_w = W - 2 * 56 - 2 * 44
    name_font, name_lines = fit(item["name"], "BrandDisplaySemi", inner_w, 1, range(62, 39, -2))
    line_font, lines = fit(item["line"], "BrandBody", inner_w, 2, range(36, 27, -1))
    line_h = int(line_font.size * 1.3)
    card_h = 44 + name_font.size + 18 + line_h * len(lines) + 34
    box = (56, H - 56 - card_h, W - 56, H - 56)
    panel = Image.new("RGBA", (box[2] - box[0], card_h), (255, 255, 255, 236))
    panel.putalpha(rounded_mask(panel.size, 40).point(lambda v: v * 236 // 255))
    place(canvas, panel, ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2), shadow=45, blur=24, drop=10)
    y = box[1] + 44 + name_font.getmetrics()[0] - 6
    draw.text((box[0] + 44, y), name_lines[0], font=name_font, fill=rgb(ink), anchor="ls")
    y += 18 + line_h - 4
    for text in lines:
        draw.text((box[0] + 44, y), text, font=line_font, fill=rgb(ink, 205), anchor="ls")
        y += line_h
    return canvas.convert("RGB")


def carousel_mockup(image: Image.Image, label: str, palette: dict, brand: dict, page: dict) -> Image.Image:
    canvas = cover_fit(image, (W, H)).convert("RGBA")
    pill(canvas, (M, 72), fix_ro(label), font("BrandBodyBold", 30), rgb(brand["ink"]), (255, 255, 255), height=62)
    pill(canvas, (W - M, H - 72 - 54), "@" + page["handle"], font("BrandBodyBold", 26), (255, 255, 255, 225),
         rgb(brand["ink"]), height=54, anchor="right")
    return canvas.convert("RGB")


def numbered_grid(canvas: Image.Image, images: list[Image.Image], top: int, card_w: int, gap: int, ink: str,
                  accent: str, width: int) -> int:
    """Rows of up to 3 numbered cards, centered. Returns the bottom y."""
    card_h = int(card_w * 1.25)
    rows = [list(range(i, min(i + 3, len(images)))) for i in range(0, len(images), 3)]
    tilts = [-3, 2, -2, 3, -1, 2]
    y = top
    for row in rows:
        row_w = len(row) * card_w + (len(row) - 1) * gap
        x = (width - row_w) // 2
        for i in row:
            center = (x + card_w // 2, y + card_h // 2)
            place(canvas, card(images[i], (card_w, card_h), radius=26, border=10), center, angle=tilts[i % 6],
                  shadow=70, blur=18, drop=12)
            badge = Image.new("RGBA", (78, 78), (0, 0, 0, 0))
            d = ImageDraw.Draw(badge)
            d.ellipse((0, 0, 77, 77), fill=(255, 255, 255, 255))
            d.ellipse((6, 6, 71, 71), fill=rgb(accent, 255))
            d.text((39, 41), str(i + 1), font=font("BrandDisplay", 40), fill=(255, 255, 255), anchor="mm")
            place(canvas, badge, (x + 18, y + 18), shadow=50, blur=8, drop=4)
            x += card_w + gap
        y += card_h + gap + 6
    return y


def carousel_cta(copy: dict, images: list[Image.Image], palette: dict, brand: dict, page: dict) -> Image.Image:
    ink, accent = brand["ink"], palette["accent"]
    canvas = background((W, H), palette["bg"], glow=90).convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    title_font, title_lines = fit(copy["cta_title"], "BrandDisplay", W - 2 * M, 2, range(96, 59, -4))
    y = 96 + title_font.getmetrics()[0]
    for line in title_lines:
        draw.text((W // 2, y), line, font=title_font, fill=rgb(ink), anchor="ms")
        y += int(title_font.size * 1.05)
    sub_font, sub_lines = fit(copy["cta_sub"], "BrandBody", W - 2 * M, 2, range(38, 29, -1))
    y += 2
    for line in sub_lines:
        draw.text((W // 2, y), line, font=sub_font, fill=rgb(ink, 200), anchor="ms")
        y += int(sub_font.size * 1.3)
    n = len(images)
    card_w, gap = (268 if n > 3 else 300), 30
    rows = (n + 2) // 3
    grid_h = rows * int(card_w * 1.25) + (rows - 1) * (gap + 6)
    pill_top = H - 118
    numbered_grid(canvas, images, int(y + (pill_top - y - grid_h) / 2), card_w, gap, ink, accent, W)
    shop_pill(canvas, page["cta_line"], pill_top, accent)
    return canvas.convert("RGB")


def shop_pill(canvas: Image.Image, text: str, y: int, accent: str, width: int = W, height: int = 84) -> None:
    fnt = font("BrandBodyBold", 32)
    text = fix_ro(text)
    while fnt.getlength(text) > width - 2 * M - 64 and fnt.size > 22:
        fnt = font("BrandBodyBold", fnt.size - 1)
    pill(canvas, (width // 2, y), text, fnt, rgb(accent), (255, 255, 255), height=height, pad_x=32, anchor="center")


# ---------------------------------------------------------------------------------------------- reel

def reel_hook(text: str, palette: dict, brand: dict) -> Image.Image:
    """Transparent full-frame overlay: the hook as a big tilted sticker label (upper third)."""
    layer = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    fnt, lines = fit(text, "BrandDisplay", RW - 2 * 110, 3, range(84, 51, -4))
    label = multiline_label(lines, fnt, "#FFFFFF", brand["ink"], palette["accent"])
    place(layer, label, (RW // 2, 470), angle=-2.5, shadow=80, blur=18, drop=10)
    return layer


def multiline_label(lines: list[str], fnt, fill: str, color: str, accent: str, pad: int = 34) -> Image.Image:
    ascent, descent = fnt.getmetrics()
    leading = int(fnt.size * 1.08)
    w = int(max(fnt.getlength(line) for line in lines) + 2 * pad)
    h = int(leading * len(lines) + pad * 1.4)
    edge = 10
    tile = Image.new("RGBA", (w + 2 * edge, h + 2 * edge), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle((0, 0, tile.width - 1, tile.height - 1), 36 + edge, fill=rgb(accent, 255))
    d.rounded_rectangle((edge, edge, edge + w - 1, edge + h - 1), 36, fill=rgb(fill, 255))
    y = edge + pad * 0.7 + ascent - fnt.size * 0.06
    for line in lines:
        d.text((tile.width / 2, y), line, font=fnt, fill=rgb(color), anchor="ms")
        y += leading
    return tile


def reel_label(name: str, index: int, palette: dict, brand: dict) -> Image.Image:
    """Transparent overlay with the sticker's number and name (top-left, inside the Reels safe area)."""
    layer = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    fnt = font("BrandBodyBold", 42)
    box = pill(layer, (M, 256), fix_ro(name), fnt, (255, 255, 255, 242), rgb(brand["ink"]), height=80,
               pad_x=34, pad_left=104)
    badge = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    d = ImageDraw.Draw(badge)
    d.ellipse((0, 0, 95, 95), fill=(255, 255, 255, 255))
    d.ellipse((7, 7, 88, 88), fill=rgb(palette["accent"], 255))
    d.text((48, 51), str(index), font=font("BrandDisplay", 48), fill=(255, 255, 255), anchor="mm")
    place(layer, badge, (box[0] + 40, (box[1] + box[3]) // 2), shadow=50, blur=10, drop=4)
    return layer


def reel_end_card(copy: dict, frames: list[Image.Image], palette: dict, brand: dict, page: dict) -> Image.Image:
    ink, accent = brand["ink"], palette["accent"]
    canvas = background((RW, RH), palette["bg"], glow=90).convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    title_font, title_lines = fit(copy["end_title"], "BrandDisplay", RW - 2 * M, 2, range(100, 63, -4))
    y = 330 + title_font.getmetrics()[0]
    for line in title_lines:
        draw.text((RW // 2, y), line, font=title_font, fill=rgb(ink), anchor="ms")
        y += int(title_font.size * 1.05)
    sub_font, sub_lines = fit(copy["end_sub"], "BrandBody", RW - 2 * M, 2, range(40, 31, -1))
    for line in sub_lines:
        draw.text((RW // 2, y + 6), line, font=sub_font, fill=rgb(ink, 200), anchor="ms")
        y += int(sub_font.size * 1.3)
    numbered_grid(canvas, frames, y + 60, 290 if len(frames) <= 3 else 250, 28, ink, accent, RW)
    shop_pill(canvas, page["cta_line"], 1470, accent, width=RW, height=92)
    draw.text((RW // 2, 1640), "@" + page["handle"], font=font("BrandBodyBold", 32), fill=rgb(ink, 190), anchor="ms")
    return canvas.convert("RGB")


def reel_cover(hook: str, frame: Image.Image, palette: dict, brand: dict, page: dict) -> Image.Image:
    canvas = cover_fit(frame, (RW, RH)).convert("RGBA")
    shade = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle((0, 0, RW, RH), fill=(20, 16, 40, 40))
    canvas.alpha_composite(shade)
    fnt, lines = fit(hook, "BrandDisplay", RW - 2 * 110, 3, range(96, 59, -4))
    place(canvas, multiline_label(lines, fnt, "#FFFFFF", brand["ink"], palette["accent"]), (RW // 2, RH // 2),
          angle=-2.5, shadow=90, blur=20, drop=12)
    pill(canvas, (RW // 2, RH // 2 + 330), "@" + page["handle"], font("BrandBodyBold", 32), (255, 255, 255, 230),
         rgb(brand["ink"]), height=66, anchor="center")
    return canvas.convert("RGB")


def contact_sheet(paths: list, out, thumb_w: int = 270) -> None:
    """One preview image of all slides (used in logs and the GitHub run summary)."""
    thumbs = [ImageOps.contain(Image.open(p).convert("RGB"), (thumb_w, int(thumb_w * 1.78))) for p in paths]
    gap = 12
    sheet = Image.new("RGB", (len(thumbs) * (thumb_w + gap) + gap, max(t.height for t in thumbs) + 2 * gap), (245, 245, 245))
    x = gap
    for t in thumbs:
        sheet.paste(t, (x, gap))
        x += thumb_w + gap
    sheet.save(out, quality=88)


def slug(text: str, limit: int = 40) -> str:
    text = fix_ro(text).lower()
    text = text.translate(str.maketrans("ăâîșț", "aaist"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:limit] or "post"
