"""Construcción de la memoria explicativa (CLAUDE.md §7.1).

Cada sección mezcla lo que escribe el Tesorero con bloques que calcula el sistema desde los datos
de la versión (así nunca contradicen las cifras). Nada de esto se guarda: se vuelve a calcular al
mostrarlo, salvo el resultado de las validaciones y los parámetros legales, que de una versión
sellada se leen de la instantánea guardada en la propuesta.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from apps.organizacion.models import Organizacion
from apps.presupuesto.calculos import Resumen, resumen_version
from apps.presupuesto.configuracion import cargar_configuracion
from apps.presupuesto.dinero import CERO, formatear_euros
from apps.presupuesto.models import Confianza, Linea, Tipo, TipoLinea, VersionPresupuesto
from apps.validaciones.motor import CATALOGO, validar_version

from .campana import construir_plan_campana
from .completitud import EstadoSeccion, estado_secciones
from .configuracion import ParametrosAnexos, SeccionCfg, parametros_de_version
from .models import ContenidoAutomatico

_DECIMA = Decimal("0.1")


class _Seguro(dict[str, str]):
    """Deja intacto un marcador desconocido en vez de fallar."""

    def __missing__(self, clave: str) -> str:
        return "{" + clave + "}"


def valores_plantilla(
    version: VersionPresupuesto, resumen: Resumen | None = None
) -> dict[str, str]:
    r = resumen or resumen_version(version)
    if r.resultado > 0:
        tipo = "superávit"
    elif r.resultado < 0:
        tipo = "déficit"
    else:
        tipo = "presupuesto equilibrado"
    return {
        "organizacion": Organizacion.obtener().nombre,
        "ejercicio": str(version.ejercicio.anio),
        "version": str(version.numero),
        "total_ingresos": formatear_euros(r.ingresos),
        "total_gastos": formatear_euros(r.gastos),
        "resultado": formatear_euros(r.resultado),
        "tipo_resultado": tipo,
        "proceso_electoral": (
            "En este ejercicio hay un proceso electoral previsto."
            if version.ejercicio.hay_proceso_electoral
            else "En este ejercicio no hay un proceso electoral previsto."
        ),
    }


def texto_inicial(cfg: SeccionCfg, version: VersionPresupuesto) -> str:
    """La plantilla de la sección con las cifras de la versión ya puestas."""
    if not cfg.plantilla.strip():
        return ""
    try:
        return cfg.plantilla.format_map(_Seguro(valores_plantilla(version)))
    except (ValueError, IndexError, KeyError, AttributeError):
        return cfg.plantilla  # llaves mal escritas en la plantilla: se ofrece tal cual


# ------------------------------------------------------------- bloques automáticos


def _porcentaje(parte: Decimal, total: Decimal) -> Decimal | None:
    if total == 0:
        return None
    return (parte * 100 / total).quantize(_DECIMA, rounding=ROUND_HALF_UP)


def bloque_resumen(version: VersionPresupuesto, params: ParametrosAnexos) -> dict[str, Any]:
    r = resumen_version(version)
    variaciones: list[dict[str, Any]] = []
    for ln in Linea.objects.filter(version=version, anulada=False).order_by("codigo"):
        ant = ln.importe_ejercicio_anterior
        if ant is None or ant == ln.importe_anual:
            continue
        dif = ln.importe_anual - ant
        variaciones.append(
            {
                "codigo": ln.codigo,
                "denominacion": ln.denominacion,
                "anterior": ant,
                "actual": ln.importe_anual,
                "diferencia": dif,
                "porcentaje": _porcentaje(dif, abs(ant)),
            }
        )
    variaciones.sort(key=lambda v: (-abs(v["diferencia"]), v["codigo"]))
    return {
        "ingresos": r.ingresos,
        "gastos": r.gastos,
        "resultado": r.resultado,
        "es_deficit": r.es_deficit,
        "explicacion": version.explicacion_resultado,
        "plan_financiacion": version.plan_financiacion,
        "variaciones": variaciones[: params.variaciones_destacadas],
        "hay_variaciones": bool(variaciones),
    }


def bloque_hipotesis(version: VersionPresupuesto) -> list[dict[str, Any]]:
    capitulos: dict[str, dict[str, Any]] = {}
    consulta = (
        Linea.objects.filter(version=version, anulada=False)
        .select_related("partida__capitulo", "hipotesis")
        .order_by("partida__capitulo__orden", "codigo")
    )
    # Ingresos primero y, dentro de cada tipo, por orden de capítulo (el orden es estable).
    lineas = sorted(consulta, key=lambda ln: ln.partida.capitulo.tipo != Tipo.INGRESO)
    for ln in lineas:
        cap = ln.partida.capitulo
        c = capitulos.setdefault(cap.codigo, {"capitulo": cap, "total": CERO, "lineas": []})
        c["total"] += ln.importe_anual
        h = getattr(ln, "hipotesis", None)
        c["lineas"].append(
            {
                "codigo": ln.codigo,
                "denominacion": ln.denominacion,
                "importe": ln.importe_anual,
                "hipotesis": h.texto if h else "",
                "fuente": h.fuente if h else "",
                "confianza": h.get_confianza_display() if h and h.confianza else "",
                "responsable": ln.responsable,
            }
        )
    return list(capitulos.values())


def bloque_riesgos(version: VersionPresupuesto) -> dict[str, Any]:
    ingresos = resumen_version(version).ingresos
    base = Linea.objects.filter(version=version, anulada=False).select_related("hipotesis")
    baja = [
        ln
        for ln in base.filter(partida__capitulo__tipo=Tipo.INGRESO).order_by("codigo")
        if getattr(ln, "hipotesis", None) and ln.hipotesis.confianza == Confianza.BAJA
    ]
    condicionadas = list(base.filter(tipo=TipoLinea.CONDICIONADO).order_by("codigo"))
    total_baja = sum((ln.importe_anual for ln in baja), CERO)
    return {
        "baja": baja,
        "total_baja": total_baja,
        "porcentaje_baja": _porcentaje(total_baja, ingresos),
        "condicionadas": condicionadas,
        "total_condicionadas": sum((ln.importe_anual for ln in condicionadas), CERO),
    }


def instantanea_parametros_legales(demo: bool) -> list[dict[str, Any]]:
    """Parámetros legales tal y como están ahora (se guarda una copia al proponer)."""
    salida = []
    for p in cargar_configuracion(demo).legales.values():
        verificado = (
            p.valor is not None
            and bool(p.referencia_normativa.strip())
            and p.fecha_verificacion is not None
            and bool(p.verificador.strip())
        )
        salida.append(
            {
                "clave": p.clave,
                "descripcion": p.descripcion,
                "valor": None if p.valor is None else str(p.valor),
                "unidad": p.unidad,
                "referencia": p.referencia_normativa,
                "fecha": p.fecha_verificacion.isoformat() if p.fecha_verificacion else None,
                "verificador": p.verificador,
                "verificado": verificado,
            }
        )
    return salida


def bloque_cumplimiento(version: VersionPresupuesto) -> dict[str, Any]:
    from apps.flujo.models import TransicionEstado

    titulos = {r.codigo: r.titulo for r in CATALOGO}
    instantanea = None
    if version.estado != "BORRADOR":
        t = (
            TransicionEstado.objects.filter(version=version, a_estado="PROPUESTO")
            .order_by("-id")
            .first()
        )
        if t and t.validacion:
            instantanea = {**t.validacion, "avisos_aceptados": t.avisos_aceptados}
    if instantanea is not None:
        origen = "Resultado en el momento de proponer la versión"
        superadas = instantanea.get("superadas", [])
        incidencias = instantanea.get("incidencias", [])
        aceptados = instantanea.get("avisos_aceptados", [])
        parametros = instantanea.get("parametros_legales", [])
    else:
        res = validar_version(version)
        origen = "Resultado de ahora mismo (la versión aún no está propuesta)"
        superadas = res.superadas()
        incidencias = [
            {
                "codigo": i.codigo,
                "gravedad": i.gravedad.value,
                "mensaje": i.mensaje,
                "linea": i.linea,
            }
            for i in res.incidencias
        ]
        aceptados = []
        parametros = instantanea_parametros_legales(version.es_demo)
    return {
        "origen": origen,
        "superadas": [{"codigo": c, "titulo": titulos.get(c, "")} for c in superadas],
        "incidencias": incidencias,
        "avisos_aceptados": aceptados,
        "parametros": parametros,
    }


# ------------------------------------------------------------------ memoria completa


@dataclass
class SeccionMostrada:
    estado: EstadoSeccion
    auto: Any = None
    clave_auto: str = ""

    @property
    def cfg(self) -> SeccionCfg:
        return self.estado.cfg


@dataclass
class Memoria:
    version: VersionPresupuesto
    params: ParametrosAnexos
    secciones: list[SeccionMostrada] = field(default_factory=list)

    @property
    def completa(self) -> bool:
        return all(s.estado.completa for s in self.secciones)

    @property
    def faltan(self) -> int:
        return sum(1 for s in self.secciones if not s.estado.completa)


def construir_memoria(version: VersionPresupuesto) -> Memoria:
    params = parametros_de_version(version)
    memoria = Memoria(version, params)
    for estado in estado_secciones(version, params):
        auto: Any = None
        match estado.cfg.contenido:
            case ContenidoAutomatico.RESUMEN:
                auto = bloque_resumen(version, params)
            case ContenidoAutomatico.HIPOTESIS:
                auto = bloque_hipotesis(version)
            case ContenidoAutomatico.RIESGOS:
                auto = bloque_riesgos(version)
            case ContenidoAutomatico.CAMPANA:
                auto = construir_plan_campana(version)
            case ContenidoAutomatico.CUMPLIMIENTO:
                auto = bloque_cumplimiento(version)
        memoria.secciones.append(SeccionMostrada(estado, auto, estado.cfg.contenido))
    return memoria
