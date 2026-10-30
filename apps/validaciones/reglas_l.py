"""Validaciones legales (CLAUDE.md §8.2).

Ningún límite está escrito aquí: todos salen de ``parametros_legales.yaml``. Si el parámetro que
una regla necesita no está verificado (valor, referencia, fecha y verificador), la regla **no se
da por cumplida**: bloquea e indica qué falta. Esto no es asesoramiento jurídico.
"""

from collections import defaultdict
from decimal import Decimal

from apps.presupuesto.dinero import CERO, formatear_euros
from apps.presupuesto.models import Donante, Tipo, TipoDonacion, TipoPersona
from apps.presupuesto.nif import enmascarar_nif

from .contexto import ContextoVersion, parametro_verificado, valor_decimal
from .tipos import Gravedad, Incidencia


def _inc(
    codigo: str, msg: str, linea: str | None = None, g: Gravedad = Gravedad.BLOQUEANTE
) -> Incidencia:
    return Incidencia(codigo, g, msg, linea)


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


def _acumulado_por_donante(
    ctx: ContextoVersion, capitulo: str, *, excluir_inmuebles: bool = False
) -> dict[Donante, Decimal]:
    acumulado: dict[Donante, Decimal] = defaultdict(lambda: CERO)
    for d in ctx.donaciones:
        if d.linea.partida.capitulo.codigo != capitulo:
            continue
        if excluir_inmuebles and d.tipo == TipoDonacion.ESPECIE_INMUEBLE:
            continue
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

    # Excepción del límite: donaciones en especie de inmuebles (si el parámetro está verificado).
    hay_inmuebles = any(
        d.tipo == TipoDonacion.ESPECIE_INMUEBLE
        for d in ctx.donaciones
        if d.linea.partida.capitulo.codigo == "I.4"
    )
    exentas = ctx.parametro("donaciones_inmuebles_exentas_de_limite")
    if hay_inmuebles and not parametro_verificado(exentas):
        salida += _pendientes(ctx, "L-001", ["donaciones_inmuebles_exentas_de_limite"])
    excluir = False
    if hay_inmuebles and parametro_verificado(exentas):
        assert exentas is not None
        excluir = bool(exentas.valor)
    acumulado = _acumulado_por_donante(ctx, "I.4", excluir_inmuebles=excluir)
    todos = _acumulado_por_donante(ctx, "I.4")
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
            for donante in todos:
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
    """El gasto electoral no supera el límite legal del proceso.

    Límite = habitantes de derecho × euros por habitante (+ adicional por provincia). Del gasto se
    descuenta, si se cumplen los requisitos, el envío directo subvencionado (ver ``campana.py``).
    """
    from apps.anexos.campana import construir_plan_campana, es_gasto_electoral

    gasto = [ln for ln in ctx.lineas if es_gasto_electoral(ln)]
    if not ctx.version.ejercicio.hay_proceso_electoral:
        if gasto:
            return [
                _inc(
                    "L-004",
                    "Hay gasto electoral pero el ejercicio no tiene proceso electoral previsto.",
                )
            ]
        return []
    if not gasto:
        return []
    plan = construir_plan_campana(ctx.version, ctx.cfg)
    if plan.limite is None:
        return [
            _inc("L-004", f"No se puede comprobar el límite de gasto electoral: falta {falta}.")
            for falta in plan.limite_pendiente
        ]
    if plan.supera_el_limite:
        return [
            _inc(
                "L-004",
                f"El gasto electoral previsto ({formatear_euros(plan.gasto_computable)}) supera "
                f"el límite ({formatear_euros(plan.limite)}).",
            )
        ]
    return []


def l012(ctx: ContextoVersion) -> list[Incidencia]:
    """Nadie aporta a las cuentas electorales más del máximo legal por persona (LOREG art. 129)."""
    from apps.anexos.campana import aportaciones_de_campana_por_persona

    aportaciones = aportaciones_de_campana_por_persona(ctx.version)
    if not aportaciones:
        return []
    p = ctx.parametro("limite_aportacion_electoral_por_persona")
    if not parametro_verificado(p):
        return _pendientes(ctx, "L-012", ["limite_aportacion_electoral_por_persona"])
    assert p is not None
    limite = valor_decimal(p)
    return [
        _inc(
            "L-012",
            f"{_quien(donante)} aporta {formatear_euros(total)} a las cuentas electorales y el "
            f"límite por persona es {formatear_euros(limite)}.",
        )
        for donante, total in sorted(aportaciones.items(), key=lambda x: x[0].nombre)
        if total > limite
    ]


def l013(ctx: ContextoVersion) -> list[Incidencia]:
    """Aviso: la subvención electoral presupuestada no puede superar el gasto electoral.

    LOREG art. 127.1: la subvención no sobrepasa los gastos electorales declarados y justificados.
    """
    from apps.anexos.campana import construir_plan_campana

    if not ctx.version.ejercicio.hay_proceso_electoral:
        return []
    plan = construir_plan_campana(ctx.version, ctx.cfg)
    if plan.subvenciones > plan.gasto_total:
        return [
            _inc(
                "L-013",
                f"La subvención electoral presupuestada ({formatear_euros(plan.subvenciones)}) "
                f"supera el gasto electoral previsto ({formatear_euros(plan.gasto_total)}): la "
                "ley no la concede por encima de los gastos justificados.",
                g=Gravedad.AVISO,
            )
        ]
    return []


def l014(ctx: ContextoVersion) -> list[Incidencia]:
    """Aviso: la subvención electoral presupuestada supera la estimada con las previsiones."""
    from apps.anexos.campana import construir_plan_campana

    if not ctx.version.ejercicio.hay_proceso_electoral:
        return []
    plan = construir_plan_campana(ctx.version, ctx.cfg)
    if plan.proceso is None or plan.subvenciones == 0:
        return []
    if plan.subvencion_estimada_pendiente:
        return [
            _inc(
                "L-014",
                "No se puede comparar la subvención con la estimada: el parámetro "
                f"«{plan.subvencion_estimada_pendiente[0]}» está pendiente de verificación.",
                g=Gravedad.AVISO,
            )
        ]
    if plan.subvencion_estimada is not None and plan.subvenciones > plan.subvencion_estimada:
        return [
            _inc(
                "L-014",
                f"La subvención electoral presupuestada ({formatear_euros(plan.subvenciones)}) "
                f"supera la estimada con las previsiones de concejales y votos "
                f"({formatear_euros(plan.subvencion_estimada)}). Solo deben presupuestarse "
                "ingresos con base cierta.",
                g=Gravedad.AVISO,
            )
        ]
    return []


def l015(ctx: ContextoVersion) -> list[Incidencia]:
    """Aviso: gasto de campaña en meses fuera del periodo electoral (LOREG art. 130)."""
    from apps.anexos.campana import construir_plan_campana

    if not ctx.version.ejercicio.hay_proceso_electoral:
        return []
    plan = construir_plan_campana(ctx.version, ctx.cfg)
    pe = plan.proceso
    if pe is None or pe.fecha_convocatoria is None or pe.fecha_proclamacion is None:
        return []
    anio = ctx.version.ejercicio.anio
    inicio = (pe.fecha_convocatoria.year, pe.fecha_convocatoria.month)
    fin = (pe.fecha_proclamacion.year, pe.fecha_proclamacion.month)
    fuera = [
        m + 1
        for m, importe in enumerate(plan.gasto_mensual)
        if importe != 0 and not (inicio <= (anio, m + 1) <= fin)
    ]
    if not fuera:
        return []
    meses = ", ".join(f"{m:02d}/{anio}" for m in fuera)
    return [
        _inc(
            "L-015",
            f"Hay gasto de campaña presupuestado fuera del periodo electoral "
            f"({pe.fecha_convocatoria:%d/%m/%Y} a {pe.fecha_proclamacion:%d/%m/%Y}), en: {meses}. "
            "Solo son gastos electorales los de ese periodo.",
            g=Gravedad.AVISO,
        )
    ]


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
    hay_elecciones = ctx.version.ejercicio.hay_proceso_electoral
    for clave, p in ctx.cfg.legales.items():
        if p.informativo or (p.ambito == "ELECTORAL" and not hay_elecciones):
            continue  # no condiciona ninguna regla de esta versión
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


def l008(ctx: ContextoVersion) -> list[Incidencia]:
    """Aviso: donaciones y aportaciones que hay que notificar al Tribunal de Cuentas.

    Según el extracto de la ley aportado por el Tesorero: donaciones superiores al umbral y todas
    las de inmuebles (art. 5.Dos); aportaciones que, individual o acumuladamente, lo superen
    (art. 8.Tres). Es un aviso: recuerda la obligación, no la comprueba.
    """
    donaciones = [d for d in ctx.donaciones if d.linea.partida.capitulo.codigo == "I.4"]
    aportaciones = _acumulado_por_donante(ctx, "I.2")
    if not donaciones and not aportaciones:
        return []
    p = ctx.parametro("umbral_notificacion_tribunal_cuentas")
    if not parametro_verificado(p):
        return [
            _inc(
                "L-008",
                "No se puede comprobar qué donaciones o aportaciones hay que notificar al "
                "Tribunal de Cuentas: el parámetro «umbral_notificacion_tribunal_cuentas» está "
                "pendiente de verificación.",
                g=Gravedad.AVISO,
            )
        ]
    assert p is not None
    umbral = valor_decimal(p)
    salida = []
    for d in donaciones:
        if d.importe > umbral or d.tipo == TipoDonacion.ESPECIE_INMUEBLE:
            salida.append(
                _inc(
                    "L-008",
                    f"La donación de {_quien(d.donante)} ({formatear_euros(d.importe)}) debe "
                    "notificarse al Tribunal de Cuentas.",
                    d.linea.codigo,
                    Gravedad.AVISO,
                )
            )
    for donante, total in aportaciones.items():
        if total > umbral:
            salida.append(
                _inc(
                    "L-008",
                    f"Las aportaciones de {_quien(donante)} suman {formatear_euros(total)} y "
                    "deben notificarse al Tribunal de Cuentas.",
                    g=Gravedad.AVISO,
                )
            )
    return salida


def l009(ctx: ContextoVersion) -> list[Incidencia]:
    """Los ingresos de actividades propias de umbral o más exigen identificar al transmitente.

    Como el presupuesto trabaja con importes anuales, el Tesorero declara en cada línea de I.5 la
    parte que procede de operaciones individuales que alcanzan el umbral; esa parte debe estar
    cubierta por donantes identificados. Una línea inferior al umbral no puede contener ninguna.
    """
    lineas = ctx.lineas_de_capitulo("I.5")
    if not lineas:
        return []
    clave = "umbral_identificacion_actividades_propias"
    p = ctx.parametro(clave)
    if not parametro_verificado(p):
        return _pendientes(ctx, "L-009", [clave])
    assert p is not None
    umbral = valor_decimal(p)
    salida = []
    for ln in lineas:
        if ln.importe_anual < umbral:
            continue
        if ln.operaciones_altas is None:
            salida.append(
                _inc(
                    "L-009",
                    f"Declara qué parte del ingreso procede de operaciones individuales de "
                    f"{formatear_euros(umbral)} o más (0,00 € si ninguna).",
                    ln.codigo,
                )
            )
            continue
        identificado = sum((d.importe for d in ctx.donaciones_de(ln)), CERO)
        if identificado < ln.operaciones_altas:
            salida.append(
                _inc(
                    "L-009",
                    f"Hay {formatear_euros(ln.operaciones_altas - identificado)} de operaciones "
                    f"individuales de {formatear_euros(umbral)} o más sin identificar al "
                    "transmitente.",
                    ln.codigo,
                )
            )
    return salida


def l010(ctx: ContextoVersion) -> list[Incidencia]:
    """No se aceptan donaciones de personas físicas parte de un contrato público vigente."""
    donantes = {
        d.donante
        for d in ctx.donaciones
        if d.linea.partida.capitulo.codigo == "I.4" and d.donante.contratista_publico
    }
    if not donantes:
        return []
    clave = "donaciones_contratistas_publicos_permitidas"
    p = ctx.parametro(clave)
    if not parametro_verificado(p):
        return _pendientes(ctx, "L-010", [clave])
    assert p is not None
    if bool(p.valor):
        return []
    return [
        _inc(
            "L-010",
            f"{_quien(d)} es parte de un contrato público vigente y no se admiten sus donaciones.",
        )
        for d in sorted(donantes, key=lambda x: x.nombre)
    ]


def l011(ctx: ContextoVersion) -> list[Incidencia]:
    """No se aceptan donaciones finalistas ni revocables."""
    marcadas = [
        d
        for d in ctx.donaciones
        if d.linea.partida.capitulo.codigo == "I.4" and (d.finalista or d.revocable)
    ]
    if not marcadas:
        return []
    clave = "donaciones_finalistas_o_revocables_permitidas"
    p = ctx.parametro(clave)
    if not parametro_verificado(p):
        return _pendientes(ctx, "L-011", [clave])
    assert p is not None
    if bool(p.valor):
        return []
    salida = []
    for d in marcadas:
        rasgos = " y ".join(
            x for x, activo in (("finalista", d.finalista), ("revocable", d.revocable)) if activo
        )
        salida.append(
            _inc(
                "L-011",
                f"La donación de {_quien(d.donante)} es {rasgos} y no se admiten.",
                d.linea.codigo,
            )
        )
    return salida
