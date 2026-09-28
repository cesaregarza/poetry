from zipfile import ZipFile

import pytest

from scripts.preview_instagram_carousel import read_poem, render_preview


def test_preview_preserves_unicode_line_breaks_and_escapes_html(tmp_path):
    source = tmp_path / "poem.html"
    source.write_text(
        '<header class="poem-header"><h1>Rain &amp; &lt;light&gt;</h1>'
        '<p class="dedication">for Ana</p></header>'
        '<div class="poem-text">  café &amp; rain\n\nnext line</div>',
        encoding="utf-8",
    )
    assert read_poem(source) == ("Rain & <light>", "  café & rain\n\nnext line", "Ana")
    output = tmp_path / "output"
    result = render_preview(source, output, "poetry.example")
    assert result["slides"] == 1
    assert result["words"] == 5
    assert "Rain &amp; &lt;light&gt;" in (output / "preview.html").read_text()
    with ZipFile(output / "rain-light-instagram-carousel.zip") as archive:
        assert archive.read("rain-light-01.png") == (output / "rain-light-01.png").read_bytes()
    with pytest.raises(FileExistsError):
        render_preview(source, output, "poetry.example")


@pytest.mark.parametrize("html", ["<html></html>", '<div class="poem-text"> </div>'])
def test_preview_rejects_missing_or_empty_poem_before_writing(tmp_path, html):
    source = tmp_path / "poem.html"
    source.write_text(html)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="nonempty"):
        render_preview(source, output, "poetry.example")
    assert not output.exists()
