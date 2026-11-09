"""Conservative lexical normalization of material experiment fields.

No inference of missing measurement methods, phases or physical properties.
Original sourced text remains unchanged; normalized values are used only for
comparability rules.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

def normalized_text(value: str | None) -> str:
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())

def normalized_temperature(value: str | None) -> str:
    text = normalized_text(value)
    expression = re.fullmatch(
        r"([+-]?\d+(?:\.\d+)?)\s*(?:°?c|celsius|k|kelvin)", text
    )
    if not expression:
        return text
    try:
        number = Decimal(expression.group(1))
    except InvalidOperation:
        return text
    if text.endswith("kelvin") or text.endswith("k"):
        number -= Decimal("273.15")
    return f"{number.normalize()} c"

def normalized_field(name: str, value: str | None) -> str:
    if name == "preparation_temperature":
        return normalized_temperature(value)
    return normalized_text(value)
