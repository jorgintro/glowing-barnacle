"""Validaciones aritméticas y de coherencia (CLAUDE.md §8.1)."""

from decimal import Decimal

from apps.presupuesto.dinero import CERO, formatear_euros
from apps.presupuesto.models import Tipo

from .contexto import ContextoVersion
from .tipos import Gravedad, Incidencia

_CENT = Decimal("0.01")


def _inc(
    codigo: str, msg: str, linea: str | None = None, g: Gravedad = Gravedad.BLOQUEANTE
) -> Incidencia:
    return Incidencia(codigo, g, msg, linea)


def v001(ctx: ContextoVersion) -> list[Incidencia]:
    """La suma de los meses de cada línea es igual al importe anual."""
    salida = []
    for ln in ctx.lineas:
        meses = ctx.mensuales.get(ln.pk, [])
        if sorted(m.mes for m in meses) != list(range(1, 13)):
            salida.append(
                _inc("V-001", "Faltan importes mensuales (deben ser los 12 meses).", ln.codigo)
            )
            continue
        suma = sum((m.importe for m in meses), CERO)
        if suma != ln.importe_anual:
            salida.append(
                _inc(
                    "V-001",
                    f"Los meses suman {formatear_euros(suma)} y el importe anual es "
                    f"{formatear_euros(ln.importe_anual)}.",
                    ln.codigo,
                )
            )
    return salida


def v002(ctx: ContextoVersion) -> list[Incidencia]:
    """Los totales de capítulo coinciden con la suma de sus líneas.

    El total de un capítulo se calcula dos veces, por el importe anual de sus líneas y por la
    suma de sus meses; si no coinciden, algún dato está descuadrado.
    """
    salida = []
    for t in ctx.resumen.capitulos:
        por_meses = sum(t.mensual, CERO)
        if t.num_lineas and por_meses != t.total:
            salida.append(
                _inc(
                    "V-002",
                    f"Capítulo {t.capitulo.codigo}: el total anual es {formatear_euros(t.total)} "
                    f"pero la suma de sus meses es {formatear_euros(por_meses)}.",
                )
            )
    return salida


def v003(ctx: ContextoVersion) -> list[Incidencia]:
    """Toda línea tiene una cuenta del PGC válida (activa y propia de su partida)."""
    salida = []
    for ln in ctx.lineas:
        c = ln.cuenta_pgc
        if c is None:
            salida.append(_inc("V-003", "No tiene cuenta del PGC.", ln.codigo))
        elif not c.activa:
            salida.append(_inc("V-003", f"La cuenta {c.codigo} ya no está activa.", ln.codigo))
        elif not ln.partida.cuentas.filter(pk=c.pk).exists():
            salida.append(
                _inc(
                    "V-003",
                    f"La cuenta {c.codigo} no corresponde a la partida {ln.partida.codigo}.",
                    ln.codigo,
                )
            )
    return salida


def v004(ctx: ContextoVersion) -> list[Incidencia]:
    """Toda línea tiene hipótesis (con fuente) y responsable; los ingresos, su confianza."""
    salida = []
    for ln in ctx.lineas:
        h = getattr(ln, "hipotesis", None)
        if h is None or not h.texto.strip():
            salida.append(_inc("V-004", "Falta la hipótesis.", ln.codigo))
        elif not h.fuente.strip():
            salida.append(_inc("V-004", "Falta la fuente de la hipótesis.", ln.codigo))
        if not ln.responsable.strip():
            salida.append(_inc("V-004", "Falta el responsable.", ln.codigo))
        if ln.partida.capitulo.tipo == Tipo.INGRESO and (h is None or not h.confianza):
            salida.append(
                _inc("V-004", "Falta la confianza en la estimación del ingreso.", ln.codigo)
            )
    return salida


def _dos_decimales(valor: Decimal) -> bool:
    return valor == valor.quantize(_CENT)


def v005(ctx: ContextoVersion) -> list[Incidencia]:
    """Importes con dos decimales y sin negativos, salvo ajustes justificados."""
    salida = []
    for ln in ctx.lineas:
        valores = [ln.importe_anual, *(m.importe for m in ctx.mensuales.get(ln.pk, []))]
        if ln.importe_ejercicio_anterior is not None:
            valores.append(ln.importe_ejercicio_anterior)
        if not all(_dos_decimales(v) for v in valores):
            salida.append(_inc("V-005", "Hay importes con más de dos decimales.", ln.codigo))
        negativos = any(v < 0 for v in valores)
        if negativos and not (ln.es_ajuste and ln.justificacion_ajuste.strip()):
            salida.append(
                _inc(
                    "V-005",
                    "Hay importes negativos y no es un ajuste justificado.",
                    ln.codigo,
                )
            )
    return salida


def v006(ctx: ContextoVersion) -> list[Incidencia]:
    """Resultado presupuestario calculado y explicado; un déficit exige plan de financiación."""
    salida = []
    v = ctx.version
    if not v.explicacion_resultado.strip():
        salida.append(_inc("V-006", "Falta la explicación del resultado presupuestario."))
    if ctx.resumen.es_deficit and not v.plan_financiacion.strip():
        salida.append(
            _inc(
                "V-006",
                f"El presupuesto tiene un déficit de {formatear_euros(-ctx.resumen.resultado)} "
                "y falta el plan de financiación.",
            )
        )
    return salida


def v007(ctx: ContextoVersion) -> list[Incidencia]:
    """Aviso: una variación grande respecto al ejercicio anterior exige justificación."""
    umbral = ctx.cfg.internos.umbral_variacion_porcentaje
    con_anterior = [ln for ln in ctx.lineas if ln.importe_ejercicio_anterior is not None]
    if umbral is None:
        if not con_anterior:
            return []
        return [
            _inc(
                "V-007",
                "El umbral de variación no está configurado (config/parametros_internos.yaml): "
                "no se puede comprobar.",
                g=Gravedad.AVISO,
            )
        ]
    salida = []
    for ln in con_anterior:
        anterior = ln.importe_ejercicio_anterior
        assert anterior is not None
        if anterior == 0:
            supera = ln.importe_anual != 0
            texto = "pasa de 0,00 € a " + formatear_euros(ln.importe_anual)
        else:
            variacion = abs(ln.importe_anual - anterior) * 100 / abs(anterior)
            supera = variacion > umbral
            texto = f"varía un {variacion.quantize(Decimal('0.1'))} % (umbral {umbral} %)"
        if supera and not ln.justificacion_variacion.strip():
            salida.append(
                _inc(
                    "V-007",
                    f"Respecto al ejercicio anterior {texto} y no está justificado.",
                    ln.codigo,
                    Gravedad.AVISO,
                )
            )
    return salida
