#!/usr/bin/env python3
"""Render a saved poetry page into PNGs, a ZIP, and an HTML preview without a database."""

import argparse
import json
import os
import sys
from html import escape
from pathlib import Path
from zipfile import ZipFile

from bs4 import BeautifulSoup


def read_poem(path):
    page = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    title = page.select_one(".poem-header h1")
    body = page.select_one(".poem-text")
    if title is None or body is None or not title.get_text().strip() or not body.get_text().strip():
        raise ValueError("HTML must contain a nonempty .poem-header h1 and .poem-text.")
    dedication = page.select_one(".poem-header .dedication")
    return (
        title.get_text(),
        body.get_text(),
        dedication.get_text().removeprefix("for ") if dedication else "",
    )


def render_preview(source, output_dir, footer, *, screenshot=False):
    from django.utils.text import slugify

    from poems.social_cards import instagram_carousel_layouts, render_instagram_slide

    title, body, dedication = read_poem(source)
    layouts = instagram_carousel_layouts(title, body, dedication)
    rendered_text = "".join(line for layout in layouts for line in layout.body_lines)
    if "".join(body.split()) != "".join(rendered_text.split()):
        raise ValueError("Rendered text does not preserve the poem's characters in order.")
    output_dir.mkdir(parents=True, exist_ok=False)
    stem = slugify(title) or "poem"
    filenames = []
    with ZipFile(output_dir / f"{stem}-instagram-carousel.zip", "w") as archive:
        for number in range(1, len(layouts) + 1):
            filename = f"{stem}-{number:02d}.png"
            payload = render_instagram_slide(title, body, dedication, footer, number)
            (output_dir / filename).write_bytes(payload)
            archive.writestr(filename, payload)
            filenames.append(filename)
    images = "".join(
        f'<img src="{escape(filename)}" alt="Slide {number}">'
        for number, filename in enumerate(filenames, 1)
    )
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{escape(title)} — carousel preview</title><style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 24px; background: #e4dfd7; }}
main {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
img {{ display: block; width: 100%; height: auto; box-shadow: 0 3px 12px #201d1b18; }}
</style></head><body><main>{images}</main></body></html>"""
    preview = output_dir / "preview.html"
    preview.write_text(html, encoding="utf-8")
    if screenshot:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1168, "height": 100})
            page.goto(preview.resolve().as_uri())
            page.wait_for_function(
                "Array.from(document.images).every(image => image.complete && image.naturalWidth)"
            )
            page.screenshot(
                path=str(output_dir / "preview.jpg"),
                type="jpeg",
                quality=85,
                full_page=True,
            )
            browser.close()
    return {
        "title": title,
        "slides": len(layouts),
        "body_font_size": layouts[0].body_font_size,
        "words": len(body.split()),
        "output_dir": str(output_dir.resolve()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", required=True, type=Path, help="Saved public poem HTML")
    parser.add_argument(
        "--output-dir", required=True, type=Path, help="New directory for the preview"
    )
    parser.add_argument("--footer", required=True, help="Site domain printed on each slide")
    parser.add_argument("--screenshot", action="store_true", help="Also capture a Chromium preview")
    args = parser.parse_args()
    if not args.footer.strip():
        parser.error("--footer must not be empty")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "poetry_site.settings")
    try:
        result = render_preview(args.html, args.output_dir, args.footer, screenshot=args.screenshot)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
