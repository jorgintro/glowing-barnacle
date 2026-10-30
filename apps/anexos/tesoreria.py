"""Plan de tesorería mensual (CLAUDE.md §7.2).

Hipótesis de partida (se muestra en pantalla): cada importe se cobra o se paga en el mes en que
está presupuestado. El saldo inicial lo introduce el Tesorero: el sistema no lleva contabilidad y
no puede conocerlo.

Escenarios:
* base: tal cual está presupuestado;
* prudente: se descuenta a los ingresos un % según la confianza de cada línea;
* ajustado: se descuenta a los gastos un % según el tipo de cada línea (recurrente, etc.).
Los porcentajes se fijan en el panel «Anexos». Sin porcentajes, el escenario no se calcula.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from apps.presupuesto.dinero import CERO, redondear
from apps.presupuesto.models import ImporteMensual, Tipo, VersionPresupuesto

from .configuracion import ParametrosAnexos, parametros_de_version

BASE, PRUDENTE, AJUSTADO = "BASE", "PRUDENTE", "AJUSTADO"
NOMBRES = {
    BASE: "Base",
    PRUDENTE: "Prudente (menos ingresos)",
    AJUSTADO: "Ajustado (menos gastos)",
}
MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]  # fmt: skip


@dataclass
class MesTesoreria:
    mes: int
    cobros: Decimal = CERO
    pagos: Decimal = CERO
    saldo: Decimal | None = None
    motivo_tension: str = ""

    @property
    def nombre(self) -> str:
        return MESES[self.mes - 1]

    @property
    def flujo(self) -> Decimal:
        return self.cobros - self.pagos

    @property
    def en_tension(self) -> bool:
        return bool(self.motivo_tension)


@dataclass
class Escenario:
    clave: str
    configurado: bool
    meses: list[MesTesoreria] = field(default_factory=list)

    @property
    def nombre(self) -> str:
        return NOMBRES[self.clave]

    @property
    def total_cobros(self) -> Decimal:
        return sum((m.cobros for m in self.meses), CERO)

    @property
    def total_pagos(self) -> Decimal:
        return sum((m.pagos for m in self.meses), CERO)

    @property
    def flujo_total(self) -> Decimal:
        return self.total_cobros - self.total_pagos

    @property
    def saldo_final(self) -> Decimal | None:
        return self.meses[-1].saldo if self.meses else None

    @property
    def meses_en_tension(self) -> list[MesTesoreria]:
        return [m for m in self.meses if m.en_tension]


@dataclass
class PlanTesoreria:
    version: VersionPresupuesto
    saldo_inicial: Decimal | None
    saldo_minimo: Decimal | None
    escenarios: list[Escenario]

    def escenario(self, clave: str) -> Escenario:
        return next(e for e in self.escenarios if e.clave == clave)


def _descontar(importe: Decimal, porcentaje: Decimal | None) -> Decimal:
    if not porcentaje:
        return importe
    return redondear(importe * (Decimal(100) - porcentaje) / Decimal(100))


def _escenario(
    clave: str,
    importes: list[ImporteMensual],
    params: ParametrosAnexos,
    saldo_inicial: Decimal | None,
) -> Escenario:
    configurado = {
        BASE: True,
        PRUDENTE: params.prudente_configurado,
        AJUSTADO: params.ajustado_configurado,
    }[clave]
    esc = Escenario(clave, configurado)
    if not configurado:
        return esc
    esc.meses = [MesTesoreria(m) for m in range(1, 13)]
    for im in importes:
        linea = im.linea
        mes = esc.meses[im.mes - 1]
        if linea.partida.capitulo.tipo == Tipo.INGRESO:
            pct = None
            if clave == PRUDENTE:
                h = getattr(linea, "hipotesis", None)
                pct = params.reduccion_ingresos.get(h.confianza) if h else None
            mes.cobros += _descontar(im.importe, pct)
        else:
            pct = params.reduccion_gastos.get(linea.tipo) if clave == AJUSTADO else None
            mes.pagos += _descontar(im.importe, pct)
    saldo = saldo_inicial
    for mes in esc.meses:
        if saldo is None:
            continue
        saldo += mes.flujo
        mes.saldo = saldo
        if saldo < 0:
            mes.motivo_tension = "saldo negativo"
        elif params.saldo_minimo is not None and saldo < params.saldo_minimo:
            mes.motivo_tension = "saldo por debajo del mínimo"
    return esc


def calcular_plan(
    version: VersionPresupuesto, params: ParametrosAnexos | None = None
) -> PlanTesoreria:
    params = params or parametros_de_version(version)
    importes = list(
        ImporteMensual.objects.filter(linea__version=version, linea__anulada=False)
        .select_related("linea__partida__capitulo", "linea__hipotesis")
        .order_by("linea__codigo", "mes")
    )
    escenarios = [
        _escenario(clave, importes, params, version.saldo_inicial_tesoreria)
        for clave in (BASE, PRUDENTE, AJUSTADO)
    ]
    return PlanTesoreria(version, version.saldo_inicial_tesoreria, params.saldo_minimo, escenarios)
