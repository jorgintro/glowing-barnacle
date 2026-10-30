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
from .models import ParametrosAnexosCfg, SeccionMemoria, SeccionMemoriaCfg


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
    if cfg is None or not cfg.aplicables_a(version.ejercicio.hay_proceso_electoral):
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


def copiar_anexos(origen: VersionPresupuesto, destino: VersionPresupuesto, *, saldo: bool) -> int:
    """Copia la memoria (marcada como pendiente de revisar) y, si procede, el saldo inicial."""
    n = 0
    for s in SeccionMemoria.objects.filter(version=origen):
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
    return n


# ------------------------------------------------------- configuración (panel Anexos)


def _datos_seccion(s: SeccionMemoriaCfg) -> dict[str, Any]:
    return {
        "titulo": s.titulo,
        "orden": s.orden,
        "obligatoria": s.obligatoria,
        "activa": s.activa,
        "longitud_minima": s.longitud_minima,
        "solo_con_proceso_electoral": s.solo_con_proceso_electoral,
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
    solo_con_proceso_electoral: bool,
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
    cfg.solo_con_proceso_electoral = solo_con_proceso_electoral
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
