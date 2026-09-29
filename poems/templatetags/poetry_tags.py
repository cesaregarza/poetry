from django import template

register = template.Library()


@register.filter
def poem_lines(value):
    """Keep authored line endings and whitespace while styling each line separately."""
    for line in value.splitlines(keepends=True):
        text = line.rstrip("\r\n")
        yield text, line[len(text) :]
