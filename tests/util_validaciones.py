"""Ayudas para las pruebas del motor de validaciones."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

from apps.anexos import servicios as anexos
from apps.anexos.configuracion import parametros_actuales
from apps.auditoria.servicios import Contexto
from apps.presupuesto import donantes as dn
from apps.presupuesto import servicios as ps
from apps.presupuesto.configuracion import (
    ConfiguracionVersion,
    ParametroCfg,
    cargar_configuracion,
)
from apps.presupuesto.models import CuentaPGC, Donante, Linea, Partida, VersionPresupuesto
from apps.validaciones.motor import validar_version
from apps.validaciones.tipos import ResultadoValidacion

HOY = date(2026, 10, 29)
LETRAS = "TRWAGMYFPDXBNJZSQVHLCKE"


def nif(n: int) -> str:
    """NIF con letra de control correcta (los números son de pruebas)."""
    return f"{n:08d}{LETRAS[n % 23]}"


def cfg_demo() -> ConfiguracionVersion:
    """Configuración de demostración: parámetros ficticios, todos verificados."""
    return cargar_configuracion(True)


def con_param(cfg: ConfiguracionVersion, clave: str, **cambios: Any) -> ConfiguracionVersion:
    nuevo: ParametroCfg = replace(cfg.legales[clave], **cambios)
    return replace(cfg, legales={**cfg.legales, clave: nuevo})


def sin_verificar(cfg: ConfiguracionVersion, clave: str) -> ConfiguracionVersion:
    return con_param(cfg, clave, valor=None, referencia_normativa="", verificador="")


def validar(
    version: VersionPresupuesto, cfg: ConfiguracionVersion | None = None
) -> ResultadoValidacion:
    return validar_version(version, cfg=cfg or cfg_demo(), hoy=HOY)


def codigos(res: ResultadoValidacion) -> set[str]:
    return {i.codigo for i in res.incidencias}


def linea(
    ctx: Contexto,
    version: VersionPresupuesto,
    partida: str,
    importe: str,
    *,
    confianza: str = "",
    cuenta: str | None = None,
    **extra: Any,
) -> Linea:
    p = Partida.objects.get(codigo=partida)
    c = CuentaPGC.objects.get(codigo=cuenta) if cuenta else p.cuentas.order_by("codigo").first()
    assert c is not None
    return ps.guardar_linea(
        ctx,
        version,
        partida=p,
        denominacion=extra.pop("denominacion", f"Línea {partida}"),
        cuenta=c,
        importe_anual=Decimal(importe),
        hipotesis=ps.DatosHipotesis("Hipótesis de prueba", "Fuente de prueba", confianza),
        responsable="Tesorería",
        **extra,
    )


def donante(ctx: Contexto, n: int, tipo: str = "FISICA", nombre: str | None = None) -> Donante:
    """Crea el donante n, o devuelve el que ya existe (se reutiliza entre versiones)."""
    existente = Donante.objects.filter(
        nif=nif(n) if tipo == "FISICA" else f"B{n:07d}1", es_demo=False
    ).first()
    if existente is not None:
        return existente
    if tipo == "JURIDICA":
        return dn.crear_donante(
            ctx, nombre=nombre or f"Empresa {n}", nif=f"B{n:07d}1", tipo_persona=tipo
        )
    return dn.crear_donante(ctx, nombre=nombre or f"Donante {n}", nif=nif(n))


def completar_anexos(ctx: Contexto, version: VersionPresupuesto) -> None:
    """Memoria escrita en todas sus secciones y saldo inicial de tesorería."""
    params = parametros_actuales(version.es_demo)
    for cfg in params.aplicables(version.ejercicio.hay_proceso_electoral):
        if not cfg.solo_automatica:
            anexos.guardar_seccion(ctx, version, cfg.clave, "Texto de prueba. " * 20)
    anexos.guardar_saldo_inicial(ctx, version, Decimal("100000"))
    if params.saldo_minimo is None:  # la configuración real no trae ningún valor
        anexos.guardar_parametros(ctx, demo=version.es_demo, saldo_minimo_tesoreria=Decimal("500"))


def presupuesto_valido(
    ctx: Contexto, version: VersionPresupuesto, campana: bool = False
) -> dict[str, Linea]:
    """Un presupuesto que supera todas las reglas con la configuración de demostración."""
    ls: dict[str, Linea] = {}
    ls["cuotas"] = linea(ctx, version, "I.1.1", "6000", confianza="ALTA")
    ls["cargos"] = linea(ctx, version, "I.2.1", "1800", confianza="MEDIA")
    ls["subv"] = linea(ctx, version, "I.3.1", "3000", confianza="MEDIA")
    ls["dona"] = linea(ctx, version, "I.4.1", "1000", confianza="BAJA")
    ls["alquiler"] = linea(ctx, version, "G.2.1", "4800")
    ls["personal"] = linea(ctx, version, "G.1.1", "3000")
    a, b, c, d = (donante(ctx, n) for n in (1, 2, 3, 4))
    dn.registrar_donacion(ctx, version, ls["cargos"], a, Decimal("900"))
    dn.registrar_donacion(ctx, version, ls["cargos"], b, Decimal("900"))
    dn.registrar_donacion(ctx, version, ls["dona"], c, Decimal("600"))
    dn.registrar_donacion(ctx, version, ls["dona"], d, Decimal("400"))
    if campana:
        ls["subv_elec"] = linea(
            ctx,
            version,
            "I.3.3",
            "6000",
            confianza="BAJA",
            dimension="CAMPANA",
            tipo="CONDICIONADO",
        )
        ls["campana"] = linea(ctx, version, "G.7.1", "5000", tipo="EXTRAORDINARIO")
    dn.guardar_resultado(
        ctx,
        version,
        explicacion="Superávit de prueba.",
        plan_financiacion="",
        endeudamiento=Decimal("0"),
    )
    completar_anexos(ctx, version)
    return ls
