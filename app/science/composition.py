"""使用 pymatgen 校验和规范化化学式及元素条件。"""

from pymatgen.core import Composition, Element

_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def normalize_formula(formula: str) -> str:
    try:
        composition = Composition(formula.strip().translate(_SUBSCRIPTS), strict=True)
        if not composition.elements or any(amount <= 0 for amount in composition.values()):
            raise ValueError("nonpositive composition")
        return composition.reduced_formula
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("请提供有效化学式，例如 TiO2、ZnO 或 Fe2O3。") from exc


def normalize_elements(elements: list[str]) -> list[str]:
    try:
        return list(dict.fromkeys(Element(item.strip()).symbol for item in elements))
    except (ValueError, TypeError) as exc:
        raise ValueError("元素必须使用有效符号，例如 O、Ti、Zn。") from exc
