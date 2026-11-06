"""Convert assistant Markdown to the HTML subset accepted by Telegram."""

import re


_TELEGRAM_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_TELEGRAM_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_TELEGRAM_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_TELEGRAM_ITALIC_STAR = re.compile(
    r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])"
)
_TELEGRAM_ITALIC_UNDERSCORE = re.compile(
    r"(?<![\w])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w])"
)
_TELEGRAM_LINK_URL = re.compile(r"\]\((https?://[^\s)]+)\)")
_TELEGRAM_LINK = re.compile(r"\[([^\]\n]+)\]\((\d+)\x02\)")
_TELEGRAM_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_TELEGRAM_RULE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_TELEGRAM_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_TELEGRAM_QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")
_TELEGRAM_TABLE_RULE = re.compile(r"^:?-{2,}:?$")


def telegram_escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def telegram_inline(text):
    """Convert inline Markdown of an already escaped line into Telegram HTML."""
    codes = []

    def stash_code(match):
        codes.append(match.group(1))
        return f"\x01{len(codes) - 1}\x01"

    text = _TELEGRAM_INLINE_CODE.sub(stash_code, text)
    urls = []

    def stash_url(match):
        urls.append(match.group(1))
        return f"]({len(urls) - 1}\x02)"

    text = _TELEGRAM_LINK_URL.sub(stash_url, text)
    text = _TELEGRAM_BOLD.sub(r"<b>\1</b>", text)
    text = _TELEGRAM_STRIKE.sub(r"<s>\1</s>", text)
    text = _TELEGRAM_ITALIC_STAR.sub(r"<i>\1</i>", text)
    text = _TELEGRAM_ITALIC_UNDERSCORE.sub(r"<i>\1</i>", text)
    text = _TELEGRAM_LINK.sub(
        lambda match: '<a href="{}">{}</a>'.format(
            urls[int(match.group(2))].replace('"', "&quot;"), match.group(1),
        ),
        text,
    )
    return re.sub(
        r"\x01(\d+)\x01",
        lambda match: "<code>{}</code>".format(codes[int(match.group(1))]),
        text,
    )


def markdown_to_telegram_html(text):
    """Turn assistant Markdown into the HTML subset Telegram can render."""
    if not isinstance(text, str):
        text = ""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output = []
    code_lines = []
    in_code = False
    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                output.append(
                    "<pre>" + telegram_escape("\n".join(code_lines)) + "</pre>"
                )
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            output.append("")
            continue
        heading = _TELEGRAM_HEADING.match(line)
        if heading:
            output.append(
                "<b>" + telegram_inline(telegram_escape(heading.group(1))) + "</b>"
            )
            continue
        if _TELEGRAM_RULE.match(line):
            output.append("─" * 12)
            continue
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if cells and all(
                _TELEGRAM_TABLE_RULE.match(cell) for cell in cells if cell
            ):
                continue
            output.append(
                " · ".join(
                    telegram_inline(telegram_escape(cell)) for cell in cells if cell
                )
            )
            continue
        bullet = _TELEGRAM_BULLET.match(line)
        if bullet:
            output.append(
                bullet.group(1)
                + "• "
                + telegram_inline(telegram_escape(bullet.group(2)))
            )
            continue
        quote = _TELEGRAM_QUOTE.match(line)
        if quote:
            output.append(
                "<blockquote>"
                + telegram_inline(telegram_escape(quote.group(1)))
                + "</blockquote>"
            )
            continue
        output.append(telegram_inline(telegram_escape(line)))
    if in_code:
        output.append("<pre>" + telegram_escape("\n".join(code_lines)) + "</pre>")
    return "\n".join(output)


def telegram_chunks(text, limit):
    """Split Markdown on line boundaries so converted messages stay valid."""
    chunk = []
    size = 0
    for line in text.split("\n"):
        while len(line) > limit:
            if chunk:
                yield "\n".join(chunk)
                chunk = []
                size = 0
            yield line[:limit]
            line = line[limit:]
        extra = len(line) + (1 if chunk else 0)
        if chunk and size + extra > limit:
            yield "\n".join(chunk)
            chunk = []
            size = 0
            extra = len(line)
        chunk.append(line)
        size += extra
    if chunk:
        yield "\n".join(chunk)
