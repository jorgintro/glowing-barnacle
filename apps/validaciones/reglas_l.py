"""Validaciones legales (CLAUDE.md §8.2).

Ningún límite está escrito aquí: todos salen de ``parametros_legales.yaml``. Si el parámetro que
una regla necesita no está verificado (valor, referencia, fecha y verificador), la regla **no se
da por cumplida**: bloquea e indica qué falta. Esto no es asesoramiento jurídico.
"""

from collections import defaultdict
from decimal import Decimal

from apps.presupuesto.dinero import CERO, formatear_euros
from apps.presupuesto.models import Dimension, Donante, Tipo, TipoPersona
from apps.presupuesto.nif import enmascarar_nif

from .contexto import ContextoVersion, parametro_verificado, valor_decimal
from .tipos import Gravedad, Incidencia


def _inc(codigo: str, msg: str, linea: str | None = None) -> Incidencia:
    return Incidencia(codigo, Gravedad.BLOQUEANTE, msg, linea)


def _quien(donante: Donante) -> str:
    """Nombre y NIF enmascarado: los avisos los ve también la Comisión Permanente."""
    return f"{donante.nombre} ({enmascarar_nif(donante.nif)})"


def _pendientes(ctx: ContextoVersion, codigo: str, claves: list[str]) -> list[Incidencia]:
    """Una incidencia por cada parámetro necesario que no esté verificado."""
    return [
        _inc(
            codigo,
            f"No se puede comprobar: el parámetro legal «{c}» está pendiente de verificación "
            "(config/parametros_legales.yaml).",
        )
        for c in claves
        if not parametro_verificado(ctx.parametro(c))
    ]


def _acumulado_por_donante(ctx: ContextoVersion, capitulo: str) -> dict[Donante, Decimal]:
    acumulado: dict[Donante, Decimal] = defaultdict(lambda: CERO)
    for d in ctx.donaciones:
        if d.linea.partida.capitulo.codigo == capitulo:
            acumulado[d.donante] += d.importe
    return acumulado


def _identificacion(
    ctx: ContextoVersion, codigo: str, capitulo: str, *, exige: bool
) -> list[Incidencia]:
    """Importe sin donante identificado en cada línea del capítulo."""
    salida = []
    for ln in ctx.lineas_de_capitulo(capitulo):
        identificado = sum((d.importe for d in ctx.donaciones_de(ln)), CERO)
        if identificado > ln.importe_anual:
            salida.append(
                _inc(
                    codigo,
                    f"Las aportaciones identificadas ({formatear_euros(identificado)}) superan "
                    f"el importe de la línea ({formatear_euros(ln.importe_anual)}).",
                    ln.codigo,
                )
            )
        elif exige and identificado < ln.importe_anual:
            salida.append(
                _inc(
                    codigo,
                    f"Hay {formatear_euros(ln.importe_anual - identificado)} sin donante "
                    "identificado.",
                    ln.codigo,
                )
            )
    return salida


def l001(ctx: ContextoVersion) -> list[Incidencia]:
    """Donaciones: límite anual por donante, identificación y tipo de persona permitidos."""
    if not ctx.lineas_de_capitulo("I.4"):
        return []
    claves = [
        "limite_donacion_anual_por_donante",
        "donaciones_anonimas_permitidas",
        "donaciones_personas_juridicas_permitidas",
    ]
    faltan = _pendientes(ctx, "L-001", claves)
    salida = list(faltan)
    anonimas = ctx.parametro("donaciones_anonimas_permitidas")
    juridicas = ctx.parametro("donaciones_personas_juridicas_permitidas")
    limite_p = ctx.parametro("limite_donacion_anual_por_donante")

    if parametro_verificado(anonimas):
        assert anonimas is not None
        salida += _identificacion(ctx, "L-001", "I.4", exige=not bool(anonimas.valor))
    else:  # al menos se vigila la incoherencia
        salida += _identificacion(ctx, "L-001", "I.4", exige=False)

    acumulado = _acumulado_por_donante(ctx, "I.4")
    if parametro_verificado(limite_p):
        assert limite_p is not None
        limite = valor_decimal(limite_p)
        for donante, total in acumulado.items():
            if total > limite:
                salida.append(
                    _inc(
                        "L-001",
                        f"{_quien(donante)} acumula {formatear_euros(total)} en "
                        f"el año y el límite por donante es {formatear_euros(limite)}.",
                    )
                )
    if parametro_verificado(juridicas):
        assert juridicas is not None
        if not bool(juridicas.valor):
            for donante in acumulado:
                if donante.tipo_persona == TipoPersona.JURIDICA:
                    salida.append(
                        _inc(
                            "L-001",
                            f"{_quien(donante)} es persona jurídica y no se "
                            "admiten donaciones de personas jurídicas.",
                        )
                    )
    return salida


def l002(ctx: ContextoVersion) -> list[Incidencia]:
    """No hay ingresos de fuentes prohibidas."""
    ingresos = [ln for ln in ctx.lineas if ln.partida.capitulo.tipo == Tipo.INGRESO]
    if not ingresos:
        return []
    p = ctx.parametro("fuentes_ingreso_prohibidas")
    if not parametro_verificado(p):
        return _pendientes(ctx, "L-002", ["fuentes_ingreso_prohibidas"])
    assert p is not None
    prohibidas = {str(x).strip().upper() for x in (p.valor or [])}
    return [
        _inc(
            "L-002",
            f"El origen «{ln.origen_ingreso}» figura entre las fuentes de ingreso prohibidas.",
            ln.codigo,
        )
        for ln in ingresos
        if ln.origen_ingreso.strip().upper() in prohibidas
    ]


def l003(ctx: ContextoVersion) -> list[Incidencia]:
    """Aportaciones de cargos públicos: identificadas y dentro del límite aplicable.

    Interpretación a confirmar con el asesor: el límite se aplica por aportante y año.
    """
    if not ctx.lineas_de_capitulo("I.2"):
        return []
    salida = _identificacion(ctx, "L-003", "I.2", exige=True)
    p = ctx.parametro("limite_aportaciones_cargos_anual")
    if not parametro_verificado(p):
        return salida + _pendientes(ctx, "L-003", ["limite_aportaciones_cargos_anual"])
    assert p is not None
    limite = valor_decimal(p)
    for donante, total in _acumulado_por_donante(ctx, "I.2").items():
        if total > limite:
            salida.append(
                _inc(
                    "L-003",
                    f"{_quien(donante)} aporta {formatear_euros(total)} en el año "
                    f"y el límite es {formatear_euros(limite)}.",
                )
            )
    return salida


def l004(ctx: ContextoVersion) -> list[Incidencia]:
    """El gasto electoral no supera el límite legal del proceso."""
    gasto = [
        ln
        for ln in ctx.lineas
        if ln.partida.capitulo.tipo == Tipo.GASTO
        and (ln.dimension == Dimension.CAMPANA or ln.partida.capitulo.codigo == "G.7")
    ]
    total = sum((ln.importe_anual for ln in gasto), CERO)
    if not ctx.version.ejercicio.hay_proceso_electoral:
        if gasto:
            return [
                _inc(
                    "L-004",
                    "Hay gasto electoral pero el ejercicio no tiene proceso electoral previsto.",
                )
            ]
        return []
    if total == 0:
        return []
    p = ctx.parametro("limite_gasto_electoral")
    if not parametro_verificado(p):
        return _pendientes(ctx, "L-004", ["limite_gasto_electoral"])
    assert p is not None
    limite = valor_decimal(p)
    if total > limite:
        return [
            _inc(
                "L-004",
                f"El gasto electoral previsto ({formatear_euros(total)}) supera el límite "
                f"({formatear_euros(limite)}).",
            )
        ]
    return []


def l005(ctx: ContextoVersion) -> list[Incidencia]:
    """El endeudamiento previsto es compatible con las condiciones legales de crédito."""
    deuda = ctx.version.endeudamiento_previsto
    if deuda == 0:
        return []
    p = ctx.parametro("limite_endeudamiento")
    if not parametro_verificado(p):
        return _pendientes(ctx, "L-005", ["limite_endeudamiento"])
    assert p is not None
    limite = valor_decimal(p)
    if deuda > limite:
        return [
            _inc(
                "L-005",
                f"El endeudamiento previsto ({formatear_euros(deuda)}) supera el límite "
                f"({formatear_euros(limite)}).",
            )
        ]
    return []


def l006(ctx: ContextoVersion) -> list[Incidencia]:
    """El presupuesto sigue la estructura del cuadro de cuentas adaptado (y este está validado)."""
    salida = []
    cuadro = ctx.cfg.cuadro
    if not cuadro.validado:
        salida.append(
            _inc(
                "L-006",
                "El cuadro de cuentas está pendiente de validación por el Tesorero o su asesor "
                "(config/cuadro_cuentas.yaml).",
            )
        )
    estructura = {p.codigo: set(p.cuentas) for c in cuadro.capitulos for p in c.partidas}
    for ln in ctx.lineas:
        codigo = ln.partida.codigo
        if codigo not in estructura or not ln.partida.activa or not ln.partida.capitulo.activo:
            salida.append(
                _inc("L-006", f"La partida {codigo} no figura en el cuadro de cuentas.", ln.codigo)
            )
        elif ln.cuenta_pgc is not None and ln.cuenta_pgc.codigo not in estructura[codigo]:
            salida.append(
                _inc(
                    "L-006",
                    f"La cuenta {ln.cuenta_pgc.codigo} no está prevista para la partida {codigo}.",
                    ln.codigo,
                )
            )
    return salida


def l007(ctx: ContextoVersion) -> list[Incidencia]:
    """Los parámetros legales están verificados y con fecha de verificación vigente.

    Interpretación a confirmar: la verificación debe ser del año del ejercicio o del anterior
    (CLAUDE.md §14: se verifica en octubre para el ejercicio siguiente) y no puede ser futura.
    """
    salida = []
    anio = ctx.version.ejercicio.anio
    for clave, p in ctx.cfg.legales.items():
        if not parametro_verificado(p):
            salida.append(
                _inc("L-007", f"El parámetro legal «{clave}» está pendiente de verificación.")
            )
            continue
        f = p.fecha_verificacion
        assert f is not None
        if f > ctx.hoy:
            salida.append(
                _inc("L-007", f"El parámetro «{clave}» tiene una fecha de verificación futura.")
            )
        elif ctx.cfg.internos.exigir_ventana_verificacion and f.year not in (anio - 1, anio):
            salida.append(
                _inc(
                    "L-007",
                    f"El parámetro «{clave}» se verificó el {f:%d/%m/%Y}: no es vigente para el "
                    f"ejercicio {anio}.",
                )
            )
    return salida
