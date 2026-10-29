"""Datos de una versión cargados una sola vez para evaluar todas las reglas."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.presupuesto.calculos import Resumen, resumen_version
from apps.presupuesto.configuracion import ConfiguracionVersion, ParametroCfg, cargar_configuracion
from apps.presupuesto.models import Donacion, ImporteMensual, Linea, VersionPresupuesto


@dataclass
class ContextoVersion:
    version: VersionPresupuesto
    cfg: ConfiguracionVersion
    hoy: date
    lineas: list[Linea]  # activas (no anuladas)
    mensuales: dict[int, list[ImporteMensual]]
    donaciones: list[Donacion]  # no anuladas
    resumen: Resumen

    def parametro(self, clave: str) -> ParametroCfg | None:
        return self.cfg.legales.get(clave)

    def donaciones_de(self, linea: Linea) -> list[Donacion]:
        return [d for d in self.donaciones if d.linea_id == linea.pk]

    def lineas_de_capitulo(self, codigo: str) -> list[Linea]:
        return [ln for ln in self.lineas if ln.partida.capitulo.codigo == codigo]


def construir_contexto(
    version: VersionPresupuesto,
    *,
    cfg: ConfiguracionVersion | None = None,
    hoy: date | None = None,
) -> ContextoVersion:
    cfg = cfg or cargar_configuracion(version.es_demo)
    lineas = list(
        Linea.objects.filter(version=version, anulada=False)
        .select_related("partida__capitulo", "cuenta_pgc", "hipotesis")
        .order_by("codigo")
    )
    mensuales: dict[int, list[ImporteMensual]] = {}
    for m in ImporteMensual.objects.filter(linea__in=[ln.pk for ln in lineas]).order_by("mes"):
        mensuales.setdefault(m.linea_id, []).append(m)
    donaciones = list(
        Donacion.objects.filter(version=version, anulada=False).select_related("donante", "linea")
    )
    return ContextoVersion(
        version=version,
        cfg=cfg,
        hoy=hoy or timezone.localdate(),
        lineas=lineas,
        mensuales=mensuales,
        donaciones=donaciones,
        resumen=resumen_version(version),
    )


def parametro_verificado(p: ParametroCfg | None) -> bool:
    """Un parámetro legal solo vale si tiene valor, referencia, fecha y verificador."""
    return (
        p is not None
        and p.valor is not None
        and bool(p.referencia_normativa.strip())
        and p.fecha_verificacion is not None
        and bool(p.verificador.strip())
    )


def valor_decimal(p: ParametroCfg) -> Decimal:
    return Decimal(str(p.valor))
