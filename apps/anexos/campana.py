"""Presupuesto de campaña (CLAUDE.md §7.3).

Calcula, a partir de las líneas de la versión y de los datos del proceso electoral:
* el límite legal de gasto (habitantes × euros por habitante, más el adicional por provincia);
* el gasto electoral y la parte de envío directo que queda fuera del límite;
* la financiación de la campaña y la parte que cubren los fondos ordinarios;
* el calendario legal orientativo.

Ninguna cifra legal está aquí: salen de los parámetros de ``config/parametros_legales.yaml``. Un
parámetro sin verificar nunca se da por bueno: lo que depende de él lo dice expresamente.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from apps.presupuesto.configuracion import ConfiguracionVersion, ParametroCfg, cargar_configuracion
from apps.presupuesto.dinero import CERO, formatear_euros, redondear
from apps.presupuesto.models import (
    Dimension,
    Donacion,
    Donante,
    ImporteMensual,
    Linea,
    Tipo,
    VersionPresupuesto,
)

from .models import ProcesoElectoral

CAPITULO_GASTOS_ELECTORALES = "G.7"


def verificado(p: ParametroCfg | None) -> bool:
    return (
        p is not None
        and p.valor is not None
        and bool(p.referencia_normativa.strip())
        and p.fecha_verificacion is not None
        and bool(p.verificador.strip())
    )


def _dec(cfg: ConfiguracionVersion, clave: str) -> Decimal | None:
    """Valor del parámetro SOLO si está verificado."""
    p = cfg.legales.get(clave)
    return Decimal(str(p.valor)) if verificado(p) and p is not None else None


def _dec_informativo(cfg: ConfiguracionVersion, clave: str) -> tuple[Decimal | None, bool]:
    """Valor del parámetro aunque no esté verificado, y si lo está."""
    p = cfg.legales.get(clave)
    if p is None or p.valor is None:
        return None, False
    return Decimal(str(p.valor)), verificado(p)


def es_gasto_electoral(linea: Linea) -> bool:
    return linea.partida.capitulo.tipo == Tipo.GASTO and (
        linea.dimension == Dimension.CAMPANA
        or linea.partida.capitulo.codigo == CAPITULO_GASTOS_ELECTORALES
    )


def es_ingreso_de_campana(linea: Linea) -> bool:
    return linea.partida.capitulo.tipo == Tipo.INGRESO and linea.dimension == Dimension.CAMPANA


def lineas_electorales(version: VersionPresupuesto) -> list[Linea]:
    return [
        ln
        for ln in Linea.objects.filter(version=version, anulada=False)
        .select_related("partida__capitulo", "cuenta_pgc")
        .order_by("codigo")
        if es_gasto_electoral(ln) or es_ingreso_de_campana(ln)
    ]


@dataclass
class FilaConcepto:
    partida: str
    denominacion: str
    cuentas: str
    importe: Decimal = CERO
    es_envio: bool = False
    lineas: int = 0


@dataclass
class Hito:
    nombre: str
    desde: date | None
    hasta: date | None
    detalle: str
    verificado: bool


@dataclass
class PlanCampana:
    version: VersionPresupuesto
    proceso: ProcesoElectoral | None
    conceptos: list[FilaConcepto] = field(default_factory=list)
    gasto_total: Decimal = CERO
    gasto_envio: Decimal = CERO
    gasto_mensual: list[Decimal] = field(default_factory=lambda: [CERO] * 12)
    # límite
    limite: Decimal | None = None
    limite_pendiente: list[str] = field(default_factory=list)  # qué falta para poder calcularlo
    exclusion_envio: Decimal = CERO
    nota_envio: str = ""
    # financiación
    subvenciones: Decimal = CERO
    aportaciones: Decimal = CERO
    otros_ingresos: Decimal = CERO
    endeudamiento: Decimal = CERO
    # estimación de la subvención según las previsiones del Tesorero
    subvencion_estimada: Decimal | None = None
    subvencion_estimada_pendiente: list[str] = field(default_factory=list)
    calendario: list[Hito] = field(default_factory=list)
    umbral_empresas: Decimal | None = None
    umbral_empresas_verificado: bool = False

    @property
    def gasto_computable(self) -> Decimal:
        return self.gasto_total - self.exclusion_envio

    @property
    def ingresos_campana(self) -> Decimal:
        return self.subvenciones + self.aportaciones + self.otros_ingresos

    @property
    def a_cubrir_con_fondos_ordinarios(self) -> Decimal:
        """Gasto de campaña que no cubren ni sus ingresos ni el endeudamiento previsto."""
        return self.gasto_total - self.ingresos_campana - self.endeudamiento

    @property
    def porcentaje_del_limite(self) -> Decimal | None:
        if self.limite is None or self.limite == 0:
            return None
        return (self.gasto_computable * 100 / self.limite).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )

    @property
    def supera_el_limite(self) -> bool:
        return self.limite is not None and self.gasto_computable > self.limite


def _limite(cfg: ConfiguracionVersion, plan: PlanCampana) -> None:
    pe = plan.proceso
    if pe is None or pe.habitantes_derecho is None:
        plan.limite_pendiente.append("el número de habitantes de derecho del proceso electoral")
        return
    tarifa = _dec(cfg, "gasto_electoral_euros_por_habitante")
    if tarifa is None:
        plan.limite_pendiente.append("verificar el parámetro «gasto_electoral_euros_por_habitante»")
        return
    limite = Decimal(pe.habitantes_derecho) * tarifa
    if pe.provincias_adicional:
        adicional = _dec(cfg, "gasto_electoral_adicional_por_provincia")
        if adicional is None:
            plan.limite_pendiente.append(
                "verificar el parámetro «gasto_electoral_adicional_por_provincia»"
            )
            return
        limite += Decimal(pe.provincias_adicional) * adicional
    plan.limite = redondear(limite)


def _exclusion_envio(cfg: ConfiguracionVersion, plan: PlanCampana) -> None:
    pe = plan.proceso
    if pe is None or not pe.subvencion_envio_aplicable or plan.gasto_envio == 0:
        return
    if pe.electores_envio is None:
        plan.nota_envio = (
            "Se indicó que se cumplen los requisitos del envío directo, pero faltan los electores: "
            "no se descuenta nada del límite."
        )
        return
    tarifa = _dec(cfg, "subvencion_envio_por_elector")
    if tarifa is None:
        plan.nota_envio = (
            "No se descuenta el envío directo del límite: el parámetro "
            "«subvencion_envio_por_elector» está pendiente de verificación."
        )
        return
    subvencion = redondear(Decimal(pe.electores_envio) * tarifa)
    plan.exclusion_envio = min(plan.gasto_envio, subvencion)
    plan.nota_envio = (
        f"Se descuenta del límite el menor entre el gasto de envío directo y su subvención "
        f"estimada ({formatear_euros(subvencion)})."
    )


def _subvencion_estimada(cfg: ConfiguracionVersion, plan: PlanCampana) -> None:
    pe = plan.proceso
    if pe is None or (pe.concejales_previstos is None and pe.votos_previstos is None):
        return
    total = CERO
    for cantidad, clave in (
        (pe.concejales_previstos, "subvencion_electoral_por_concejal"),
        (pe.votos_previstos, "subvencion_electoral_por_voto"),
    ):
        if not cantidad:
            continue
        tarifa = _dec(cfg, clave)
        if tarifa is None:
            plan.subvencion_estimada_pendiente.append(clave)
            continue
        total += Decimal(cantidad) * tarifa
    if plan.subvencion_estimada_pendiente:
        return
    if pe.subvencion_envio_aplicable and pe.electores_envio:
        tarifa = _dec(cfg, "subvencion_envio_por_elector")
        if tarifa is None:
            plan.subvencion_estimada_pendiente.append("subvencion_envio_por_elector")
            return
        total += Decimal(pe.electores_envio) * tarifa
    plan.subvencion_estimada = redondear(total)


def _calendario(cfg: ConfiguracionVersion, plan: PlanCampana) -> None:
    pe = plan.proceso
    if pe is None:
        return

    def dias(clave: str) -> tuple[int | None, bool]:
        valor, ok = _dec_informativo(cfg, clave)
        return (None if valor is None else int(valor)), ok

    if pe.fecha_convocatoria or pe.fecha_proclamacion:
        plan.calendario.append(
            Hito(
                "Periodo de gasto electoral (de la convocatoria a la proclamación de electos)",
                pe.fecha_convocatoria,
                pe.fecha_proclamacion,
                "Art. 130 de la LOREG: solo son gastos electorales los de este periodo.",
                True,
            )
        )
    if pe.fecha_convocatoria:
        d1, v1 = dias("adelanto_solicitud_desde_dias")
        d2, v2 = dias("adelanto_solicitud_hasta_dias")
        if d1 is not None and d2 is not None:
            plan.calendario.append(
                Hito(
                    "Solicitud del adelanto de la subvención",
                    pe.fecha_convocatoria + timedelta(days=d1),
                    pe.fecha_convocatoria + timedelta(days=d2),
                    "Entre los días indicados posteriores a la convocatoria (art. 127 bis).",
                    v1 and v2,
                )
            )
        d3, v3 = dias("adelanto_disponible_desde_dias")
        if d3 is not None:
            plan.calendario.append(
                Hito(
                    "El adelanto se pone a disposición a partir de",
                    pe.fecha_convocatoria + timedelta(days=d3),
                    None,
                    "Art. 127 bis.",
                    v3,
                )
            )
    if pe.fecha_elecciones:
        d1, v1 = dias("plazo_contabilidad_electoral_desde_dias")
        d2, v2 = dias("plazo_contabilidad_electoral_hasta_dias")
        if d1 is not None and d2 is not None:
            plan.calendario.append(
                Hito(
                    "Presentación de la contabilidad electoral al Tribunal de Cuentas",
                    pe.fecha_elecciones + timedelta(days=d1),
                    pe.fecha_elecciones + timedelta(days=d2),
                    "Entre los días indicados posteriores a las elecciones (art. 133). "
                    "Las entidades de crédito que concedieron crédito informan en el mismo plazo.",
                    v1 and v2,
                )
            )


def construir_plan_campana(
    version: VersionPresupuesto, cfg: ConfiguracionVersion | None = None
) -> PlanCampana:
    cfg = cfg or cargar_configuracion(version.es_demo)
    plan = PlanCampana(
        version=version,
        proceso=ProcesoElectoral.objects.filter(version=version).first(),
        endeudamiento=version.endeudamiento_previsto,
    )
    por_partida: dict[str, FilaConcepto] = {}
    ids_gasto: list[int] = []
    for ln in lineas_electorales(version):
        if es_gasto_electoral(ln):
            ids_gasto.append(ln.pk)
            fila = por_partida.setdefault(
                ln.partida.codigo,
                FilaConcepto(
                    ln.partida.codigo,
                    ln.partida.denominacion,
                    ", ".join(
                        ln.partida.cuentas.order_by("codigo").values_list("codigo", flat=True)
                    ),
                    es_envio=ln.partida.envio_electoral,
                ),
            )
            fila.importe += ln.importe_anual
            fila.lineas += 1
            plan.gasto_total += ln.importe_anual
            if ln.partida.envio_electoral:
                plan.gasto_envio += ln.importe_anual
        else:
            capitulo = ln.partida.capitulo.codigo
            if capitulo == "I.3":
                plan.subvenciones += ln.importe_anual
            elif capitulo in ("I.2", "I.4", "I.5"):
                plan.aportaciones += ln.importe_anual
            else:
                plan.otros_ingresos += ln.importe_anual
    plan.conceptos = sorted(por_partida.values(), key=lambda f: f.partida)
    for m in ImporteMensual.objects.filter(linea_id__in=ids_gasto):
        plan.gasto_mensual[m.mes - 1] += m.importe
    _limite(cfg, plan)
    _exclusion_envio(cfg, plan)
    _subvencion_estimada(cfg, plan)
    _calendario(cfg, plan)
    plan.umbral_empresas, plan.umbral_empresas_verificado = _dec_informativo(
        cfg, "umbral_informe_empresas_gasto_electoral"
    )
    return plan


def aportaciones_de_campana_por_persona(
    version: VersionPresupuesto,
) -> dict[Donante, Decimal]:
    """Lo que cada persona aporta a las cuentas electorales (donaciones en líneas de campaña)."""
    total: dict[Donante, Decimal] = {}
    for d in Donacion.objects.filter(version=version, anulada=False).select_related(
        "donante", "linea"
    ):
        if d.linea.dimension == Dimension.CAMPANA:
            total[d.donante] = total.get(d.donante, CERO) + d.importe
    return total
