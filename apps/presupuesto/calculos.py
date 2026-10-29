"""Totales del presupuesto. Todo en ``Decimal``; las anuladas no cuentan."""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, Sum

from .dinero import CERO
from .models import Capitulo, Dimension, ImporteMensual, Linea, Tipo, VersionPresupuesto


@dataclass
class TotalCapitulo:
    capitulo: Capitulo
    total: Decimal = CERO
    mensual: list[Decimal] = field(default_factory=lambda: [CERO] * 12)
    num_lineas: int = 0


@dataclass
class Resumen:
    capitulos: list[TotalCapitulo]
    ingresos: Decimal
    gastos: Decimal
    ingresos_mensual: list[Decimal]
    gastos_mensual: list[Decimal]
    gasto_campana: Decimal

    @property
    def resultado(self) -> Decimal:
        """Resultado presupuestario: positivo = superávit, negativo = déficit."""
        return self.ingresos - self.gastos

    @property
    def es_deficit(self) -> bool:
        return self.resultado < 0

    def resultado_mensual(self) -> list[Decimal]:
        return [i - g for i, g in zip(self.ingresos_mensual, self.gastos_mensual, strict=True)]


def resumen_version(version: VersionPresupuesto) -> Resumen:
    activas = Linea.objects.filter(version=version, anulada=False)
    por_capitulo = {c.codigo: TotalCapitulo(c) for c in Capitulo.objects.filter(activo=True)}

    totales = (
        activas.values("partida__capitulo__codigo")
        .order_by()
        .annotate(total=Sum("importe_anual"), n=Count("id"))
    )
    for fila_total in totales:
        destino = por_capitulo[fila_total["partida__capitulo__codigo"]]
        destino.total = fila_total["total"] or CERO
        destino.num_lineas = fila_total["n"]
    meses = (
        ImporteMensual.objects.filter(linea__version=version, linea__anulada=False)
        .values("linea__partida__capitulo__codigo", "mes")
        .annotate(total=Sum("importe"))
    )
    for fila_mes in meses:
        codigo = fila_mes["linea__partida__capitulo__codigo"]
        por_capitulo[codigo].mensual[fila_mes["mes"] - 1] = fila_mes["total"] or CERO

    def _sumar(tipo: str) -> tuple[Decimal, list[Decimal]]:
        elegidos = [t for t in por_capitulo.values() if t.capitulo.tipo == tipo]
        total = sum((t.total for t in elegidos), CERO)
        mensual = [sum((t.mensual[m] for t in elegidos), CERO) for m in range(12)]
        return total, mensual

    ingresos, ing_m = _sumar(Tipo.INGRESO)
    gastos, gas_m = _sumar(Tipo.GASTO)
    campana = activas.filter(
        partida__capitulo__tipo=Tipo.GASTO, dimension=Dimension.CAMPANA
    ).aggregate(t=Sum("importe_anual"))["t"]
    return Resumen(
        capitulos=sorted(por_capitulo.values(), key=lambda t: (t.capitulo.tipo, t.capitulo.orden)),
        ingresos=ingresos,
        gastos=gastos,
        ingresos_mensual=ing_m,
        gastos_mensual=gas_m,
        gasto_campana=campana or CERO,
    )
