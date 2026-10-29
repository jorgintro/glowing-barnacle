"""Aritmética del dinero. Prohibido ``float``: todo es ``Decimal`` con dos decimales.

Criterio de redondeo (único en todo el sistema): ``ROUND_HALF_UP`` a céntimos, es decir,
medio céntimo se redondea hacia arriba (en valor absoluto).
"""

from decimal import ROUND_HALF_UP, Decimal

CERO = Decimal("0.00")
_CENTIMO = Decimal("0.01")


def redondear(valor: Decimal) -> Decimal:
    """Redondea a céntimos con el criterio del sistema."""
    return valor.quantize(_CENTIMO, rounding=ROUND_HALF_UP)


def a_centimos(valor: Decimal) -> int:
    return int(redondear(valor) * 100)


def de_centimos(centimos: int) -> Decimal:
    return (Decimal(centimos) / 100).quantize(_CENTIMO)


def repartir_uniforme(importe: Decimal, partes: int = 12) -> list[Decimal]:
    """Reparte ``importe`` en ``partes`` cuotas cuya suma es exactamente el importe.

    Se trabaja en céntimos enteros; los céntimos sobrantes se asignan de uno en uno a los
    primeros meses (p. ej. 100,00 € en 12 meses: 4 meses de 8,34 € y 8 de 8,33 €).
    """
    total = a_centimos(importe)
    base, resto = divmod(abs(total), partes)
    signo = -1 if total < 0 else 1
    return [de_centimos(signo * (base + (1 if i < resto else 0))) for i in range(partes)]


def formatear_euros(valor: Decimal | None) -> str:
    """Formato español: ``1.234,56 €``. ``None`` se muestra como guion."""
    if valor is None:
        return "—"
    v = redondear(valor)
    signo = "-" if v < 0 else ""
    entero, decimales = f"{abs(v):.2f}".split(".")
    entero = f"{int(entero):,}".replace(",", ".")
    return f"{signo}{entero},{decimales} €"
