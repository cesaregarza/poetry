from dataclasses import dataclass
from functools import lru_cache
from hashlib import blake2s
from io import BytesIO

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

CARD_WIDTH = 1200
CARD_HEIGHT = 630
CARD_SIZE = (CARD_WIDTH, CARD_HEIGHT)
CARD_DESIGN_VERSION = "1"

INSTAGRAM_CARD_WIDTH = 1080
INSTAGRAM_CARD_HEIGHT = 1350
INSTAGRAM_CARD_SIZE = (INSTAGRAM_CARD_WIDTH, INSTAGRAM_CARD_HEIGHT)
INSTAGRAM_CARD_DESIGN_VERSION = "2"
INSTAGRAM_BODY_MAX_SIZE = 46
INSTAGRAM_BODY_MIN_SIZE = 24

BACKGROUND = "#f5f0e7"
INK = "#201d1b"
MUTED_INK = "#6e655f"
ACCENT = "#9d4f3d"
RULE = "#d8cec1"

INSTAGRAM_TEXT_LEFT = 124
INSTAGRAM_TEXT_RIGHT = 972
INSTAGRAM_TEXT_WIDTH = INSTAGRAM_TEXT_RIGHT - INSTAGRAM_TEXT_LEFT
INSTAGRAM_TITLE_TOP = 142
INSTAGRAM_BODY_BOTTOM = 1182


class InstagramCardTooLong(ValueError):
    pass


@dataclass(frozen=True)
class InstagramCardLayout:
    title_font_size: int
    title_lines: tuple[str, ...]
    title_spacing: int
    title_height: int
    dedication_top: int | None
    dedication_font_size: int | None
    dedication_lines: tuple[str, ...]
    dedication_spacing: int
    body_font_size: int
    body_lines: tuple[str, ...]
    body_line_height: int
    stanza_gap: int
    body_top: int
    body_height: int


def social_card_version(*parts):
    digest = blake2s(digest_size=6)
    digest.update(CARD_DESIGN_VERSION.encode())
    for part in parts:
        value = str(part).encode("utf-8")
        digest.update(len(value).to_bytes(4, "big"))
        digest.update(value)
    return digest.hexdigest()


def instagram_card_version(*parts):
    digest = blake2s(digest_size=6)
    digest.update(INSTAGRAM_CARD_DESIGN_VERSION.encode())
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


def _fitted_instagram_title(draw, title):
    for size in range(68, 37, -2):
        font = _font("SourceSerif4Variable-Roman.woff2", size)
        lines = _wrap_title(draw, title, font, INSTAGRAM_TEXT_WIDTH)
        spacing = round(size * 0.08)
        bounds = draw.multiline_textbbox(
            (0, 0),
            "\n".join(lines),
            font=font,
            spacing=spacing,
        )
        height = bounds[3] - bounds[1]
        if len(lines) <= 3 and height <= 220:
            return size, tuple(lines), spacing, height

    raise InstagramCardTooLong(
        "The poem title is too long to fit the Instagram card at a readable size."
    )


def _fitted_instagram_dedication(draw, dedication):
    if not dedication:
        return None, (), 0, 0

    text = f"for {dedication}"
    for size in range(25, 17, -1):
        font = _font("SourceSerif4Variable-Roman.woff2", size)
        lines = _wrap_title(draw, text, font, INSTAGRAM_TEXT_WIDTH)
        spacing = round(size * 0.12)
        bounds = draw.multiline_textbbox(
            (0, 0),
            "\n".join(lines),
            font=font,
            spacing=spacing,
        )
        height = bounds[3] - bounds[1]
        if len(lines) <= 2 and height <= 58:
            return size, tuple(lines), spacing, height

    raise InstagramCardTooLong(
        "The dedication is too long to fit the Instagram card at a readable size."
    )


def _wrap_poem_line(draw, line, font):
    line = line.expandtabs(4)
    if not line or draw.textlength(line, font=font) <= INSTAGRAM_TEXT_WIDTH:
        return [line]

    leading_space_count = len(line) - len(line.lstrip(" "))
    continuation_indent = " " * min(leading_space_count, 8)
    wrapped = []
    remainder = line

    while remainder:
        low = 1
        high = len(remainder)
        fitting_length = 1
        while low <= high:
            midpoint = (low + high) // 2
            if draw.textlength(remainder[:midpoint], font=font) <= INSTAGRAM_TEXT_WIDTH:
                fitting_length = midpoint
                low = midpoint + 1
            else:
                high = midpoint - 1

        if fitting_length == len(remainder):
            wrapped.append(remainder.rstrip())
            break

        whitespace_positions = [
            position
            for position, character in enumerate(remainder[:fitting_length], start=1)
            if character.isspace() and remainder[:position].strip()
        ]
        split_at = whitespace_positions[-1] if whitespace_positions else fitting_length
        wrapped.append(remainder[:split_at].rstrip())
        remainder = remainder[split_at:].lstrip()
        if remainder and continuation_indent:
            remainder = f"{continuation_indent}{remainder}"

    return wrapped


def _wrapped_poem_lines(draw, poem_body, font):
    normalized = poem_body.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for physical_line in normalized.split("\n"):
        lines.extend(_wrap_poem_line(draw, physical_line, font))
    return tuple(lines)


def _poem_text_height(lines, line_height, stanza_gap):
    if not lines:
        return 0
    return sum(stanza_gap if not line else line_height for line in lines)


def instagram_card_layout(title, poem_body, dedication=""):
    measuring_image = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(measuring_image)
    title_size, title_lines, title_spacing, title_height = _fitted_instagram_title(draw, title)
    dedication_size, dedication_lines, dedication_spacing, dedication_height = (
        _fitted_instagram_dedication(draw, dedication)
    )

    title_bottom = INSTAGRAM_TITLE_TOP + title_height
    dedication_top = title_bottom + 22 if dedication else None
    body_top_minimum = (
        dedication_top + dedication_height + 46 if dedication_top is not None else title_bottom + 64
    )
    available_body_height = INSTAGRAM_BODY_BOTTOM - body_top_minimum

    for body_size in range(INSTAGRAM_BODY_MAX_SIZE, INSTAGRAM_BODY_MIN_SIZE - 1, -1):
        body_font = _font("SourceSerif4Variable-Roman.woff2", body_size)
        body_lines = _wrapped_poem_lines(draw, poem_body, body_font)
        line_height = round(body_size * 1.34)
        stanza_gap = round(body_size * 0.72)
        body_height = _poem_text_height(body_lines, line_height, stanza_gap)
        if body_height <= available_body_height:
            breathing_room = max(0, available_body_height - body_height)
            body_top = body_top_minimum + min(92, breathing_room // 5)
            return InstagramCardLayout(
                title_font_size=title_size,
                title_lines=title_lines,
                title_spacing=title_spacing,
                title_height=title_height,
                dedication_top=dedication_top,
                dedication_font_size=dedication_size,
                dedication_lines=dedication_lines,
                dedication_spacing=dedication_spacing,
                body_font_size=body_size,
                body_lines=body_lines,
                body_line_height=line_height,
                stanza_gap=stanza_gap,
                body_top=body_top,
                body_height=body_height,
            )

    raise InstagramCardTooLong(
        "This poem needs more than one 1080 × 1350 card at the minimum readable "
        f"size ({INSTAGRAM_BODY_MIN_SIZE} px)."
    )


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


@lru_cache(maxsize=256)
def render_instagram_card(title, poem_body, dedication, author_name):
    layout = instagram_card_layout(title, poem_body, dedication)
    image = Image.new("RGB", INSTAGRAM_CARD_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (38, 38, INSTAGRAM_CARD_WIDTH - 38, INSTAGRAM_CARD_HEIGHT - 38),
        radius=4,
        outline=RULE,
        width=2,
    )
    draw.rectangle((76, 76, 82, INSTAGRAM_CARD_HEIGHT - 76), fill=ACCENT)

    label_font = _font("InterVariable.woff2", 19)
    draw.text(
        (INSTAGRAM_TEXT_LEFT, 82),
        "POEM",
        font=label_font,
        fill=ACCENT,
    )

    title_font = _font("SourceSerif4Variable-Roman.woff2", layout.title_font_size)
    draw.multiline_text(
        (INSTAGRAM_TEXT_LEFT, INSTAGRAM_TITLE_TOP),
        "\n".join(layout.title_lines),
        font=title_font,
        fill=INK,
        spacing=layout.title_spacing,
    )

    if layout.dedication_top is not None and layout.dedication_font_size is not None:
        dedication_font = _font(
            "SourceSerif4Variable-Roman.woff2",
            layout.dedication_font_size,
        )
        draw.multiline_text(
            (INSTAGRAM_TEXT_LEFT, layout.dedication_top),
            "\n".join(layout.dedication_lines),
            font=dedication_font,
            fill=MUTED_INK,
            spacing=layout.dedication_spacing,
        )

    body_font = _font("SourceSerif4Variable-Roman.woff2", layout.body_font_size)
    current_y = layout.body_top
    for line in layout.body_lines:
        if line:
            draw.text((INSTAGRAM_TEXT_LEFT, current_y), line, font=body_font, fill=INK)
            current_y += layout.body_line_height
        else:
            current_y += layout.stanza_gap

    draw.line(
        (INSTAGRAM_TEXT_LEFT, 1214, INSTAGRAM_TEXT_RIGHT, 1214),
        fill=RULE,
        width=2,
    )
    watermark_font = _font("InterVariable.woff2", 18)
    author_watermark = author_name.upper()
    draw.text(
        (INSTAGRAM_TEXT_LEFT, 1243),
        author_watermark,
        font=watermark_font,
        fill=MUTED_INK,
    )

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
