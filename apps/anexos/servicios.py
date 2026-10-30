"""Casos de uso de los anexos. Solo el Tesorero escribe; todo queda en la auditoría.

La auditoría no guarda el texto de la memoria (podría contener nombres): solo la clave de la
sección, su longitud y la huella del texto.
"""

import hashlib
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.servicios import Contexto, registrar
from apps.presupuesto.dinero import redondear
from apps.presupuesto.models import VersionPresupuesto
from apps.presupuesto.servicios import exigir_borrador, exigir_tesorero

from .configuracion import (
    CAMPOS_CONFIANZA,
    CAMPOS_TIPO,
    asegurar_configuracion,
    parametros_actuales,
)
from .models import ParametrosAnexosCfg, ProcesoElectoral, SeccionMemoria, SeccionMemoriaCfg


def _huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------ memoria de una versión


@transaction.atomic
def guardar_seccion(
    contexto: Contexto, version: VersionPresupuesto, clave: str, texto: str
) -> SeccionMemoria:
    """Guarda el texto de una sección (solo borradores). Guardar también la da por revisada."""
    exigir_tesorero(contexto)
    exigir_borrador(version)
    cfg = parametros_actuales(version.es_demo).seccion(clave)
    if cfg is None or not cfg.aplicables_a(version.ambito):
        raise ValidationError("Esa sección no existe o no se aplica a esta versión.")
    if cfg.solo_automatica:
        raise ValidationError(f"La sección «{cfg.titulo}» la genera el sistema: no se escribe.")
    texto = texto.strip()
    anterior = SeccionMemoria.objects.filter(version=version, clave=clave).first()
    seccion, _ = SeccionMemoria.objects.update_or_create(
        version=version,
        clave=clave,
        defaults={
            "texto": texto,
            "pendiente_revision": False,
            "actualizada_por": contexto.usuario,
            "actualizada_en": timezone.now(),
        },
    )
    registrar(
        contexto,
        accion="memoria.guardar_seccion",
        entidad="SeccionMemoria",
        entidad_id=seccion.pk,
        antes=None
        if anterior is None
        else {"caracteres": len(anterior.texto), "huella": _huella(anterior.texto)},
        despues={
            "version": version.pk,
            "seccion": clave,
            "caracteres": len(texto),
            "huella": _huella(texto),
        },
        es_demo=version.es_demo,
    )
    return seccion


@transaction.atomic
def guardar_saldo_inicial(
    contexto: Contexto, version: VersionPresupuesto, saldo: Decimal | None
) -> None:
    exigir_tesorero(contexto)
    exigir_borrador(version)
    antes = version.saldo_inicial_tesoreria
    version.saldo_inicial_tesoreria = None if saldo is None else redondear(saldo)
    version.save(update_fields=["saldo_inicial_tesoreria"])
    registrar(
        contexto,
        accion="tesoreria.guardar_saldo_inicial",
        entidad="VersionPresupuesto",
        entidad_id=version.pk,
        antes={"saldo_inicial": None if antes is None else str(antes)},
        despues={
            "saldo_inicial": None
            if version.saldo_inicial_tesoreria is None
            else str(version.saldo_inicial_tesoreria)
        },
        es_demo=version.es_demo,
    )


def copiar_anexos(
    origen: VersionPresupuesto,
    destino: VersionPresupuesto,
    *,
    saldo: bool,
    campana: bool = True,
) -> int:
    """Copia la memoria (marcada como pendiente de revisar), el saldo inicial y la campaña."""
    n = 0
    params = parametros_actuales(destino.es_demo)
    ambito = destino.ambito
    for s in SeccionMemoria.objects.filter(version=origen):
        cfg = params.seccion(s.clave)
        if cfg is None or not cfg.aplicables_a(ambito):
            continue  # la sección ya no existe o no se aplica a la versión nueva
        SeccionMemoria.objects.create(
            version=destino,
            clave=s.clave,
            texto=s.texto,
            pendiente_revision=True,
            actualizada_por=None,
            actualizada_en=timezone.now(),
        )
        n += 1
    if saldo and origen.saldo_inicial_tesoreria is not None:
        VersionPresupuesto.objects.filter(pk=destino.pk).update(
            saldo_inicial_tesoreria=origen.saldo_inicial_tesoreria
        )
        destino.saldo_inicial_tesoreria = origen.saldo_inicial_tesoreria
    pe = ProcesoElectoral.objects.filter(version=origen).first()
    if campana and pe is not None:
        ProcesoElectoral.objects.create(
            version=destino,
            denominacion=pe.denominacion,
            fecha_convocatoria=pe.fecha_convocatoria,
            fecha_elecciones=pe.fecha_elecciones,
            fecha_proclamacion=pe.fecha_proclamacion,
            habitantes_derecho=pe.habitantes_derecho,
            provincias_adicional=pe.provincias_adicional,
            subvencion_envio_aplicable=pe.subvencion_envio_aplicable,
            electores_envio=pe.electores_envio,
            concejales_previstos=pe.concejales_previstos,
            votos_previstos=pe.votos_previstos,
            observaciones=pe.observaciones,
            actualizado_por=None,
        )
    return n


CAMPOS_PROCESO = (
    "denominacion",
    "fecha_convocatoria",
    "fecha_elecciones",
    "fecha_proclamacion",
    "habitantes_derecho",
    "provincias_adicional",
    "subvencion_envio_aplicable",
    "electores_envio",
    "concejales_previstos",
    "votos_previstos",
    "observaciones",
)


def _datos_proceso(pe: ProcesoElectoral | None) -> dict[str, Any] | None:
    if pe is None:
        return None
    return {c: None if getattr(pe, c) is None else str(getattr(pe, c)) for c in CAMPOS_PROCESO}


@transaction.atomic
def guardar_proceso_electoral(
    contexto: Contexto, version: VersionPresupuesto, **datos: Any
) -> ProcesoElectoral:
    """Datos del proceso electoral de la versión (solo borradores de ejercicios con campaña)."""
    exigir_tesorero(contexto)
    exigir_borrador(version)
    if not version.es_electoral:
        raise ValidationError("Los datos del proceso electoral son del presupuesto electoral.")
    desconocidos = set(datos) - set(CAMPOS_PROCESO)
    if desconocidos:
        raise ValidationError(f"Datos desconocidos: {', '.join(sorted(desconocidos))}.")
    conv, elec, proc = (
        datos.get("fecha_convocatoria"),
        datos.get("fecha_elecciones"),
        datos.get("fecha_proclamacion"),
    )
    errores = []
    if conv and elec and elec < conv:
        errores.append("La fecha de las elecciones no puede ser anterior a la convocatoria.")
    if elec and proc and proc < elec:
        errores.append("La proclamación de electos no puede ser anterior a las elecciones.")
    if conv and proc and proc < conv:
        errores.append("La proclamación de electos no puede ser anterior a la convocatoria.")
    if errores:
        raise ValidationError(errores)
    anterior = ProcesoElectoral.objects.filter(version=version).first()
    antes = _datos_proceso(anterior)
    pe = anterior or ProcesoElectoral(version=version)
    for campo in CAMPOS_PROCESO:
        if campo in datos:
            valor = datos[campo]
            if campo in ("denominacion", "observaciones"):
                valor = (valor or "").strip()
            elif campo == "provincias_adicional":
                valor = valor or 0
            setattr(pe, campo, valor)
    pe.actualizado_por = contexto.usuario
    pe.actualizado_en = timezone.now()
    pe.save()
    registrar(
        contexto,
        accion="campana.guardar_proceso_electoral",
        entidad="ProcesoElectoral",
        entidad_id=pe.pk,
        antes=antes,
        despues={**(_datos_proceso(pe) or {}), "version": version.pk},
        es_demo=version.es_demo,
    )
    return pe


# ------------------------------------------------------- configuración (panel Anexos)


def _datos_seccion(s: SeccionMemoriaCfg) -> dict[str, Any]:
    return {
        "titulo": s.titulo,
        "orden": s.orden,
        "obligatoria": s.obligatoria,
        "activa": s.activa,
        "longitud_minima": s.longitud_minima,
        "ambito": s.ambito,
        "ayuda": _huella(s.ayuda),
        "plantilla": _huella(s.plantilla),
    }


@transaction.atomic
def guardar_seccion_cfg(
    contexto: Contexto,
    cfg: SeccionMemoriaCfg,
    *,
    titulo: str,
    orden: int,
    obligatoria: bool,
    activa: bool,
    longitud_minima: int | None,
    ambito: str,
    ayuda: str,
    plantilla: str,
) -> SeccionMemoriaCfg:
    exigir_tesorero(contexto)
    if not titulo.strip():
        raise ValidationError("La sección necesita un título.")
    antes = _datos_seccion(cfg)
    cfg.titulo = titulo.strip()
    cfg.orden = orden
    cfg.obligatoria = obligatoria
    cfg.activa = activa
    cfg.longitud_minima = longitud_minima or None
    cfg.ambito = ambito
    cfg.ayuda = ayuda.strip()
    cfg.plantilla = plantilla.rstrip()
    cfg.save()
    registrar(
        contexto,
        accion="anexos.guardar_seccion_cfg",
        entidad="SeccionMemoriaCfg",
        entidad_id=cfg.pk,
        antes=antes,
        despues=_datos_seccion(cfg),
        es_demo=cfg.es_demo,
    )
    return cfg


@transaction.atomic
def crear_seccion_cfg(contexto: Contexto, *, titulo: str, demo: bool) -> SeccionMemoriaCfg:
    """Añade una sección propia (solo texto escrito a mano) al final."""
    exigir_tesorero(contexto)
    asegurar_configuracion(demo)
    titulo = titulo.strip()
    if not titulo:
        raise ValidationError("Escribe el título de la sección nueva.")
    existentes = SeccionMemoriaCfg.objects.filter(es_demo=demo)
    n = existentes.count() + 1
    clave = f"propia-{n}"
    while existentes.filter(clave=clave).exists():
        n += 1
        clave = f"propia-{n}"
    orden = (max((s.orden for s in existentes), default=0)) + 1
    cfg = SeccionMemoriaCfg.objects.create(
        clave=clave, titulo=titulo, orden=orden, obligatoria=False, es_demo=demo
    )
    registrar(
        contexto,
        accion="anexos.crear_seccion_cfg",
        entidad="SeccionMemoriaCfg",
        entidad_id=cfg.pk,
        despues=_datos_seccion(cfg),
        es_demo=demo,
    )
    return cfg


@transaction.atomic
def restablecer_seccion_cfg(contexto: Contexto, cfg: SeccionMemoriaCfg) -> SeccionMemoriaCfg:
    """Devuelve la ayuda y la plantilla a los valores propuestos de config/memoria.yaml."""
    from .configuracion import secciones_propuestas

    exigir_tesorero(contexto)
    propuesta = next((s for s in secciones_propuestas() if s["clave"] == cfg.clave), None)
    if propuesta is None:
        raise ValidationError("Esta sección es propia: no hay valores propuestos que restablecer.")
    antes = _datos_seccion(cfg)
    cfg.titulo = propuesta["titulo"]
    cfg.obligatoria = bool(propuesta.get("obligatoria", True))
    cfg.longitud_minima = propuesta.get("longitud_minima")
    cfg.ayuda = (propuesta.get("ayuda") or "").strip()
    cfg.plantilla = (propuesta.get("plantilla") or "").rstrip()
    cfg.save()
    registrar(
        contexto,
        accion="anexos.restablecer_seccion_cfg",
        entidad="SeccionMemoriaCfg",
        entidad_id=cfg.pk,
        antes=antes,
        despues=_datos_seccion(cfg),
        es_demo=cfg.es_demo,
    )
    return cfg


def _datos_parametros(p: ParametrosAnexosCfg) -> dict[str, Any]:
    campos = [
        "variaciones_destacadas",
        "saldo_minimo_tesoreria",
        "porcentaje_aviso_limite_campana",
        "semaforo_ambar_pct",
        "semaforo_rojo_pct",
        "semaforo_importe_minimo",
        *CAMPOS_CONFIANZA.values(),
        *CAMPOS_TIPO.values(),
    ]
    datos: dict[str, Any] = {
        c: None if getattr(p, c) is None else str(getattr(p, c)) for c in campos
    }
    datos["marcas_pendiente"] = p.marcas
    return datos


@transaction.atomic
def guardar_parametros(contexto: Contexto, *, demo: bool, **valores: Any) -> ParametrosAnexosCfg:
    exigir_tesorero(contexto)
    asegurar_configuracion(demo)
    p = ParametrosAnexosCfg.objects.get(es_demo=demo)
    antes = _datos_parametros(p)
    for nombre, valor in valores.items():
        if not hasattr(p, nombre):
            raise ValidationError(f"Parámetro desconocido: {nombre}.")
        setattr(p, nombre, valor)
    p.save()
    registrar(
        contexto,
        accion="anexos.guardar_parametros",
        entidad="ParametrosAnexosCfg",
        entidad_id=p.pk,
        antes=antes,
        despues=_datos_parametros(p),
        es_demo=demo,
    )
    return p
