"""Vuelca la configuración YAML a la base de datos de forma idempotente.

Nada se borra: lo que desaparece del fichero se marca como inactivo.
"""

from dataclasses import dataclass

from django.db import transaction

from apps.auditoria.servicios import Contexto, registrar

from .configuracion import (
    CuadroCuentasCfg,
    ParametrosLegalesCfg,
    cargar_cuadro_cuentas,
    cargar_parametros_legales,
)
from .models import Capitulo, CuentaPGC, ParametroLegal, Partida


@dataclass
class Resultado:
    creados: int = 0
    actualizados: int = 0
    desactivados: int = 0

    @property
    def hubo_cambios(self) -> bool:
        return bool(self.creados or self.actualizados or self.desactivados)


def _actualizar(objeto: object, **campos: object) -> bool:
    cambio = False
    for nombre, valor in campos.items():
        if getattr(objeto, nombre) != valor:
            setattr(objeto, nombre, valor)
            cambio = True
    return cambio


@transaction.atomic
def sincronizar_cuadro_cuentas(cfg: CuadroCuentasCfg | None = None) -> Resultado:
    cfg = cfg or cargar_cuadro_cuentas()
    r = Resultado()

    cuentas = {}
    for c in cfg.cuentas:
        cuenta, creada = CuentaPGC.objects.get_or_create(
            codigo=c.codigo, defaults={"denominacion": c.denominacion}
        )
        if creada:
            r.creados += 1
        elif _actualizar(cuenta, denominacion=c.denominacion, activa=True):
            cuenta.save()
            r.actualizados += 1
        cuentas[c.codigo] = cuenta
    for vieja in CuentaPGC.objects.exclude(codigo__in=cuentas).filter(activa=True):
        vieja.activa = False
        vieja.save()
        r.desactivados += 1

    codigos_cap: list[str] = []
    codigos_par: list[str] = []
    for orden_cap, cap in enumerate(cfg.capitulos, start=1):
        codigos_cap.append(cap.codigo)
        capitulo, creado = Capitulo.objects.get_or_create(
            codigo=cap.codigo,
            defaults={
                "tipo": cap.tipo,
                "denominacion": cap.denominacion,
                "orden": orden_cap,
                "ambito": cap.ambito,
            },
        )
        if creado:
            r.creados += 1
        elif _actualizar(
            capitulo,
            tipo=cap.tipo,
            denominacion=cap.denominacion,
            orden=orden_cap,
            ambito=cap.ambito,
            activo=True,
        ):
            capitulo.save()
            r.actualizados += 1
        for orden_par, par in enumerate(cap.partidas, start=1):
            codigos_par.append(par.codigo)
            partida, creada = Partida.objects.get_or_create(
                codigo=par.codigo,
                defaults={
                    "capitulo": capitulo,
                    "denominacion": par.denominacion,
                    "orden": orden_par,
                    "dimension_por_defecto": par.dimension,
                    "envio_electoral": par.envio_electoral,
                },
            )
            if creada:
                r.creados += 1
            elif _actualizar(
                partida,
                capitulo=capitulo,
                denominacion=par.denominacion,
                orden=orden_par,
                dimension_por_defecto=par.dimension,
                envio_electoral=par.envio_electoral,
                activa=True,
            ):
                partida.save()
                r.actualizados += 1
            nuevas = {cuentas[c].pk for c in par.cuentas}
            if set(partida.cuentas.values_list("pk", flat=True)) != nuevas:
                partida.cuentas.set(nuevas)
                if not creada:
                    r.actualizados += 1
    for vieja_cap in Capitulo.objects.exclude(codigo__in=codigos_cap).filter(activo=True):
        vieja_cap.activo = False
        vieja_cap.save()
        r.desactivados += 1
    for vieja_par in Partida.objects.exclude(codigo__in=codigos_par).filter(activa=True):
        vieja_par.activa = False
        vieja_par.save()
        r.desactivados += 1
    return r


@transaction.atomic
def sincronizar_parametros_legales(cfg: ParametrosLegalesCfg | None = None) -> Resultado:
    cfg = cfg or cargar_parametros_legales()
    r = Resultado()
    claves = []
    for p in cfg.parametros:
        claves.append(p.clave)
        campos = {
            "descripcion": p.descripcion,
            "unidad": p.unidad,
            "regla": p.regla,
            "norma_orientativa": p.norma_orientativa,
            "valor": p.valor,
            "referencia_normativa": p.referencia_normativa,
            "fecha_verificacion": p.fecha_verificacion,
            "verificador": p.verificador,
            "ambito": p.ambito,
            "informativo": p.informativo,
            "activo": True,
        }
        parametro, creado = ParametroLegal.objects.get_or_create(clave=p.clave, defaults=campos)
        if creado:
            r.creados += 1
        elif _actualizar(parametro, **campos):
            parametro.save()
            r.actualizados += 1
    for viejo in ParametroLegal.objects.exclude(clave__in=claves).filter(activo=True):
        viejo.activo = False
        viejo.save()
        r.desactivados += 1
    return r


def sincronizar_todo() -> dict[str, Resultado]:
    """Sincroniza ambos ficheros y deja constancia en la auditoría si hubo cambios."""
    resultados = {
        "cuadro_cuentas": sincronizar_cuadro_cuentas(),
        "parametros_legales": sincronizar_parametros_legales(),
    }
    for nombre, res in resultados.items():
        if res.hubo_cambios:
            registrar(
                Contexto(None),
                accion="config.sincronizar",
                entidad=nombre,
                despues={
                    "creados": res.creados,
                    "actualizados": res.actualizados,
                    "desactivados": res.desactivados,
                },
                usuario_texto="sistema",
            )
    return resultados
