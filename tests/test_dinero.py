import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.presupuesto.dinero import (
    a_centimos,
    de_centimos,
    formatear_euros,
    redondear,
    repartir_uniforme,
)


def test_redondeo_medio_centimo_hacia_arriba() -> None:
    assert redondear(Decimal("0.005")) == Decimal("0.01")
    assert redondear(Decimal("0.004")) == Decimal("0.00")
    assert redondear(Decimal("-0.005")) == Decimal("-0.01")


def test_centimos_ida_y_vuelta() -> None:
    assert a_centimos(Decimal("1234.56")) == 123456
    assert de_centimos(123456) == Decimal("1234.56")


@pytest.mark.parametrize("importe", ["100.00", "0.00", "1.00", "1234.56", "9999999.99", "-100.00"])
def test_reparto_uniforme_suma_exacta(importe: str) -> None:
    cuotas = repartir_uniforme(Decimal(importe))
    assert len(cuotas) == 12
    assert sum(cuotas) == Decimal(importe)
    assert max(cuotas) - min(cuotas) <= Decimal("0.01") or Decimal(importe) < 0


def test_reparto_cien_euros() -> None:
    cuotas = repartir_uniforme(Decimal("100"))
    assert cuotas[:4] == [Decimal("8.34")] * 4
    assert cuotas[4:] == [Decimal("8.33")] * 8


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (Decimal("1234.56"), "1.234,56 €"),
        (Decimal("0"), "0,00 €"),
        (Decimal("-1234567.5"), "-1.234.567,50 €"),
        (Decimal("12"), "12,00 €"),
        (None, "—"),
    ],
)
def test_formato_espanol(valor: Decimal | None, esperado: str) -> None:
    assert formatear_euros(valor) == esperado


def test_prohibido_float_en_el_codigo() -> None:
    """CLAUDE.md §9.4: nada de ``float`` para dinero. Se vigila en todo el código de las apps."""
    raiz = Path(__file__).resolve().parent.parent / "apps"
    patron = re.compile(r"\bfloat\s*\(|:\s*float\b|->\s*float\b|FloatField")
    infractores = [
        str(f.relative_to(raiz))
        for f in raiz.rglob("*.py")
        if "migrations" not in f.parts and patron.search(f.read_text(encoding="utf-8"))
    ]
    assert infractores == []
