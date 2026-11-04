"""按来源行号精确复制原文，并检查引用范围与长度。"""

from app.schemas.selection import LineRange


def source_lines(text: str) -> list[dict]:
    return [{"line": index, "text": line} for index, line in enumerate(text.splitlines(), 1)]


def copy_range(text: str, selected: LineRange, max_length: int = 3000) -> str:
    lines = text.splitlines()
    if not 1 <= selected.start_line <= selected.end_line <= len(lines):
        raise ValueError("invalid_source_line_range")
    quote = "\n".join(lines[selected.start_line - 1 : selected.end_line])
    if not quote.strip() or len(quote) > max_length:
        raise ValueError("invalid_source_quote_length")
    return quote
