from functools import lru_cache
from hashlib import blake2s
from io import BytesIO

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

CARD_WIDTH = 1200
CARD_HEIGHT = 630
CARD_SIZE = (CARD_WIDTH, CARD_HEIGHT)
CARD_DESIGN_VERSION = "1"

BACKGROUND = "#f5f0e7"
INK = "#201d1b"
MUTED_INK = "#6e655f"
ACCENT = "#9d4f3d"
RULE = "#d8cec1"


def social_card_version(*parts):
    digest = blake2s(digest_size=6)
    digest.update(CARD_DESIGN_VERSION.encode())
    for part in parts:
        value = str(part).encode("utf-8")
        digest.update(len(value).to_bytes(4, "big"))
        digest.update(value)
    return digest.hexdigest()


@lru_cache(maxsize=64)
def _font(filename, size):
    return ImageFont.truetype(str(settings.BASE_DIR / "static" / "fonts" / filename), size)


def _wrap_title(draw, title, font, max_width):
    words = title.split()
    if not words:
        return [""]

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fitted_title(draw, title):
    max_width = 930
    for size in range(104, 51, -2):
        font = _font("SourceSerif4Variable-Roman.woff2", size)
        lines = _wrap_title(draw, title, font, max_width)
        spacing = round(size * 0.08)
        bounds = draw.multiline_textbbox(
            (0, 0),
            "\n".join(lines),
            font=font,
            spacing=spacing,
        )
        if len(lines) <= 3 and bounds[3] - bounds[1] <= 286:
            return font, lines, spacing

    font = _font("SourceSerif4Variable-Roman.woff2", 50)
    lines = _wrap_title(draw, title, font, max_width)
    if len(lines) > 3:
        lines = lines[:3]
        last_line = lines[-1]
        while last_line and draw.textlength(f"{last_line}…", font=font) > max_width:
            last_line = last_line[:-1].rstrip()
        lines[-1] = f"{last_line}…"
    return font, lines, 5


@lru_cache(maxsize=512)
def render_social_card(title, eyebrow, footer):
    image = Image.new("RGB", CARD_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (38, 38, CARD_WIDTH - 38, CARD_HEIGHT - 38),
        radius=4,
        outline=RULE,
        width=2,
    )
    draw.rectangle((88, 82, 94, CARD_HEIGHT - 82), fill=ACCENT)

    label_font = _font("InterVariable.woff2", 22)
    draw.text((126, 88), eyebrow.upper(), font=label_font, fill=ACCENT)

    title_font, title_lines, title_spacing = _fitted_title(draw, title)
    draw.multiline_text(
        (126, 158),
        "\n".join(title_lines),
        font=title_font,
        fill=INK,
        spacing=title_spacing,
    )

    draw.line((126, 507, CARD_WIDTH - 96, 507), fill=RULE, width=2)
    footer_font = _font("InterVariable.woff2", 21)
    draw.text((126, 535), footer, font=footer_font, fill=MUTED_INK)

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
