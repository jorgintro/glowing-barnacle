"""Comparativa y desviaciones (CLAUDE.md §7.4).

* Presupuesto frente al ejercicio anterior (variación absoluta y porcentual).
* Presupuesto frente a la ejecución real acumulada hasta el mes de corte, con semáforo.

El semáforo mira la desviación ADVERSA: en un ingreso, quedarse por debajo de lo presupuestado;
en un gasto, pasarse. Los umbrales se fijan en el panel «Anexos»; sin ellos no se calcula.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from apps.presupuesto.dinero import CERO
from apps.presupuesto.models import ImporteMensual, Linea, Tipo, VersionPresupuesto

from .configuracion import ParametrosAnexos, parametros_actuales
from .ejecucion import importacion_vigente
from .models import EjecucionReal, ImportacionEjecucion

VERDE, AMBAR, ROJO = "VERDE", "AMBAR", "ROJO"
SIN_DATOS, SIN_CONFIGURAR = "SIN_DATOS", "SIN_CONFIGURAR"
ETIQUETAS = {
    VERDE: "Verde",
    AMBAR: "Ámbar",
    ROJO: "Rojo",
    SIN_DATOS: "Sin datos",
    SIN_CONFIGURAR: "Sin configurar",
}
_DECIMA = Decimal("0.1")


def porcentaje(parte: Decimal, base: Decimal) -> Decimal | None:
    if base == 0:
        return None
    return (parte * 100 / abs(base)).quantize(_DECIMA, rounding=ROUND_HALF_UP)


def semaforo(
    tipo: str, presupuestado: Decimal, real: Decimal | None, params: ParametrosAnexos
) -> tuple[str, Decimal, Decimal | None]:
    """Devuelve (color, desviación adversa en euros, desviación adversa en %)."""
    if real is None:
        return SIN_DATOS, CERO, None
    adversa = presupuestado - real if tipo == Tipo.INGRESO else real - presupuestado
    pct = porcentaje(adversa, presupuestado)
    if not params.semaforo_configurado:
        return SIN_CONFIGURAR, adversa, pct
    minimo = params.semaforo_importe_minimo or CERO
    if adversa <= 0 or adversa < minimo:
        return VERDE, adversa, pct
    assert params.semaforo_ambar_pct is not None and params.semaforo_rojo_pct is not None
    if pct is None or pct >= params.semaforo_rojo_pct:  # sin base y con desviación: rojo
        return ROJO, adversa, pct
    if pct >= params.semaforo_ambar_pct:
        return AMBAR, adversa, pct
    return VERDE, adversa, pct


@dataclass
class FilaLinea:
    codigo: str
    denominacion: str
    tipo: str
    capitulo: str
    anual: Decimal
    anterior: Decimal | None
    presupuestado_corte: Decimal
    real: Decimal | None
    color: str = SIN_DATOS
    desviacion: Decimal = CERO
    desviacion_pct: Decimal | None = None

    @property
    def variacion(self) -> Decimal | None:
        return None if self.anterior is None else self.anual - self.anterior

    @property
    def variacion_pct(self) -> Decimal | None:
        if self.anterior is None or self.variacion is None:
            return None
        return porcentaje(self.variacion, self.anterior)

    @property
    def etiqueta(self) -> str:
        return ETIQUETAS[self.color]


@dataclass
class FilaCapitulo:
    codigo: str
    denominacion: str
    tipo: str
    anual: Decimal = CERO
    anterior: Decimal | None = CERO
    presupuestado_corte: Decimal = CERO
    real: Decimal | None = CERO
    lineas: list[FilaLinea] = field(default_factory=list)
    color: str = SIN_DATOS
    desviacion: Decimal = CERO
    desviacion_pct: Decimal | None = None

    @property
    def variacion(self) -> Decimal | None:
        return None if self.anterior is None else self.anual - self.anterior

    @property
    def variacion_pct(self) -> Decimal | None:
        if self.anterior is None or self.variacion is None:
            return None
        return porcentaje(self.variacion, self.anterior)

    @property
    def etiqueta(self) -> str:
        return ETIQUETAS[self.color]


@dataclass
class Comparativa:
    version: VersionPresupuesto
    importacion: ImportacionEjecucion | None
    mes_corte: int | None
    params: ParametrosAnexos
    capitulos: list[FilaCapitulo] = field(default_factory=list)

    @property
    def lineas(self) -> list[FilaLinea]:
        return [ln for c in self.capitulos for ln in c.lineas]

    def resumen_color(self) -> dict[str, int]:
        cuenta: dict[str, int] = {}
        for ln in self.lineas:
            cuenta[ln.color] = cuenta.get(ln.color, 0) + 1
        return cuenta


def construir_comparativa(
    version: VersionPresupuesto, params: ParametrosAnexos | None = None
) -> Comparativa:
    params = params or parametros_actuales(version.es_demo)
    imp = importacion_vigente(version.ejercicio)
    corte = imp.mes_corte if imp else None
    real: dict[str, Decimal] = {}
    if imp is not None:
        for r in EjecucionReal.objects.filter(importacion=imp):
            real[r.codigo_linea] = real.get(r.codigo_linea, CERO) + r.importe
    lineas = list(
        Linea.objects.filter(version=version, anulada=False)
        .select_related("partida__capitulo")
        .order_by("partida__capitulo__tipo", "partida__capitulo__orden", "codigo")
    )
    lineas.sort(
        key=lambda ln: (ln.partida.capitulo.tipo != Tipo.INGRESO, ln.partida.capitulo.orden)
    )
    mensual: dict[int, Decimal] = {}
    if corte is not None:
        for m in ImporteMensual.objects.filter(linea__in=[ln.pk for ln in lineas], mes__lte=corte):
            mensual[m.linea_id] = mensual.get(m.linea_id, CERO) + m.importe
    comp = Comparativa(version, imp, corte, params)
    capitulos: dict[str, FilaCapitulo] = {}
    for ln in lineas:
        cap = ln.partida.capitulo
        fila_cap = capitulos.setdefault(
            cap.codigo, FilaCapitulo(cap.codigo, cap.denominacion, cap.tipo)
        )
        fila = FilaLinea(
            codigo=ln.codigo,
            denominacion=ln.denominacion,
            tipo=cap.tipo,
            capitulo=cap.codigo,
            anual=ln.importe_anual,
            anterior=ln.importe_ejercicio_anterior,
            presupuestado_corte=mensual.get(ln.pk, CERO),
            real=real.get(ln.codigo) if imp else None,
        )
        fila.color, fila.desviacion, fila.desviacion_pct = semaforo(
            cap.tipo, fila.presupuestado_corte, fila.real, params
        )
        fila_cap.lineas.append(fila)
        fila_cap.anual += ln.importe_anual
        fila_cap.presupuestado_corte += fila.presupuestado_corte
        if fila_cap.anterior is not None:
            fila_cap.anterior = (
                None
                if ln.importe_ejercicio_anterior is None
                else fila_cap.anterior + ln.importe_ejercicio_anterior
            )
        if fila_cap.real is not None:
            fila_cap.real = None if fila.real is None else fila_cap.real + fila.real
    for fila_cap in capitulos.values():
        fila_cap.color, fila_cap.desviacion, fila_cap.desviacion_pct = semaforo(
            fila_cap.tipo, fila_cap.presupuestado_corte, fila_cap.real, params
        )
    comp.capitulos = list(capitulos.values())
    return comp
