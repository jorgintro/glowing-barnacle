"""Configuración de la memoria y del plan de tesorería.

Los valores viven en la base de datos y se editan desde el panel «Anexos» (solo el Tesorero).
``config/memoria.yaml`` solo SIEMBRA los valores propuestos la primera vez: lo que ya existe en la
base de datos no se pisa jamás. Hay un juego para lo real y otro, ficticio, para la demostración.

Al proponer una versión se guarda una copia (instantánea) de los parámetros usados: la versión
sellada se muestra siempre con los valores con los que se selló, aunque luego se cambien.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings
from django.db import transaction

from apps.presupuesto.configuracion import ErrorConfiguracion, directorio_config
from apps.presupuesto.models import Confianza, TipoLinea, VersionPresupuesto

from .models import ContenidoAutomatico, ParametrosAnexosCfg, SeccionMemoriaCfg

CAMPOS_CONFIANZA = {
    Confianza.ALTA: "reduccion_ingresos_alta",
    Confianza.MEDIA: "reduccion_ingresos_media",
    Confianza.BAJA: "reduccion_ingresos_baja",
}
CAMPOS_TIPO = {
    TipoLinea.RECURRENTE: "reduccion_gastos_recurrente",
    TipoLinea.EXTRAORDINARIO: "reduccion_gastos_extraordinario",
    TipoLinea.CONDICIONADO: "reduccion_gastos_condicionado",
}


@dataclass(frozen=True)
class SeccionCfg:
    clave: str
    titulo: str
    orden: int
    contenido: str
    obligatoria: bool
    solo_con_proceso_electoral: bool
    longitud_minima: int | None
    ayuda: str
    plantilla: str

    @property
    def solo_automatica(self) -> bool:
        return self.contenido == ContenidoAutomatico.CUMPLIMIENTO

    def aplicables_a(self, hay_proceso_electoral: bool) -> bool:
        return hay_proceso_electoral or not self.solo_con_proceso_electoral


@dataclass(frozen=True)
class ParametrosAnexos:
    secciones: tuple[SeccionCfg, ...]
    marcas_pendiente: tuple[str, ...] = ("[COMPLETAR", "PENDIENTE DE REVISAR")
    variaciones_destacadas: int = 5
    saldo_minimo: Decimal | None = None
    # confianza → % de reducción de ingresos (escenario prudente)
    reduccion_ingresos: dict[str, Decimal | None] = field(default_factory=dict)
    # tipo de línea → % de reducción de gastos (escenario ajustado)
    reduccion_gastos: dict[str, Decimal | None] = field(default_factory=dict)
    porcentaje_aviso_limite_campana: Decimal | None = None
    semaforo_ambar_pct: Decimal | None = None
    semaforo_rojo_pct: Decimal | None = None
    semaforo_importe_minimo: Decimal | None = None

    @property
    def semaforo_configurado(self) -> bool:
        return self.semaforo_ambar_pct is not None and self.semaforo_rojo_pct is not None

    @property
    def prudente_configurado(self) -> bool:
        return any(v is not None for v in self.reduccion_ingresos.values())

    @property
    def ajustado_configurado(self) -> bool:
        return any(v is not None for v in self.reduccion_gastos.values())

    def seccion(self, clave: str) -> SeccionCfg | None:
        return next((s for s in self.secciones if s.clave == clave), None)

    def aplicables(self, hay_proceso_electoral: bool) -> list[SeccionCfg]:
        return [s for s in self.secciones if s.aplicables_a(hay_proceso_electoral)]

    # --- instantánea (JSON) -------------------------------------------------------------

    def a_json(self) -> dict[str, Any]:
        def dec(v: Decimal | None) -> str | None:
            return None if v is None else str(v)

        return {
            "secciones": [
                {
                    "clave": s.clave,
                    "titulo": s.titulo,
                    "orden": s.orden,
                    "contenido": s.contenido,
                    "obligatoria": s.obligatoria,
                    "solo_con_proceso_electoral": s.solo_con_proceso_electoral,
                    "longitud_minima": s.longitud_minima,
                    "ayuda": s.ayuda,
                    "plantilla": s.plantilla,
                }
                for s in self.secciones
            ],
            "marcas_pendiente": list(self.marcas_pendiente),
            "variaciones_destacadas": self.variaciones_destacadas,
            "saldo_minimo": dec(self.saldo_minimo),
            "reduccion_ingresos": {k: dec(v) for k, v in self.reduccion_ingresos.items()},
            "reduccion_gastos": {k: dec(v) for k, v in self.reduccion_gastos.items()},
            "porcentaje_aviso_limite_campana": dec(self.porcentaje_aviso_limite_campana),
            "semaforo_ambar_pct": dec(self.semaforo_ambar_pct),
            "semaforo_rojo_pct": dec(self.semaforo_rojo_pct),
            "semaforo_importe_minimo": dec(self.semaforo_importe_minimo),
        }

    @classmethod
    def desde_json(cls, datos: dict[str, Any]) -> "ParametrosAnexos":
        def dec(v: str | None) -> Decimal | None:
            return None if v is None else Decimal(v)

        return cls(
            secciones=tuple(SeccionCfg(**s) for s in datos["secciones"]),
            marcas_pendiente=tuple(datos["marcas_pendiente"]),
            variaciones_destacadas=datos["variaciones_destacadas"],
            saldo_minimo=dec(datos["saldo_minimo"]),
            reduccion_ingresos={k: dec(v) for k, v in datos["reduccion_ingresos"].items()},
            reduccion_gastos={k: dec(v) for k, v in datos["reduccion_gastos"].items()},
            porcentaje_aviso_limite_campana=dec(datos.get("porcentaje_aviso_limite_campana")),
            semaforo_ambar_pct=dec(datos.get("semaforo_ambar_pct")),
            semaforo_rojo_pct=dec(datos.get("semaforo_rojo_pct")),
            semaforo_importe_minimo=dec(datos.get("semaforo_importe_minimo")),
        )


# ------------------------------------------------------------------ lectura de los YAML


def _leer(nombre: str, directorio: Path) -> dict[str, Any]:
    ruta = directorio / nombre
    try:
        with ruta.open(encoding="utf-8") as f:
            datos = yaml.safe_load(f)
    except FileNotFoundError as error:
        raise ErrorConfiguracion(f"No existe el fichero de configuración {ruta}.") from error
    except yaml.YAMLError as error:
        raise ErrorConfiguracion(f"{nombre} no es un YAML válido: {error}") from error
    if not isinstance(datos, dict):
        raise ErrorConfiguracion(f"{nombre} debe contener un diccionario en el nivel superior.")
    return datos


def _decimal(valor: object, donde: str) -> Decimal | None:
    if valor is None:
        return None
    if isinstance(valor, float | bool):
        raise ErrorConfiguracion(
            f'{donde}: escribe el número como texto entre comillas, p. ej. "20".'
        )
    try:
        return Decimal(str(valor).replace(",", "."))
    except InvalidOperation as error:
        raise ErrorConfiguracion(f"{donde}: «{valor}» no es un número.") from error


def secciones_propuestas() -> list[dict[str, Any]]:
    datos = _leer("memoria.yaml", Path(settings.CONFIG_DIR))
    secciones = datos.get("secciones")
    if not isinstance(secciones, list) or not secciones:
        raise ErrorConfiguracion("memoria.yaml: faltan las secciones de la memoria.")
    contenidos = set(ContenidoAutomatico.values)
    vistas: set[str] = set()
    for i, s in enumerate(secciones, start=1):
        donde = f"memoria.yaml, sección {i}"
        if not isinstance(s, dict) or not s.get("clave") or not s.get("titulo"):
            raise ErrorConfiguracion(f"{donde}: faltan «clave» y «titulo».")
        if s["clave"] in vistas:
            raise ErrorConfiguracion(f"{donde}: clave repetida «{s['clave']}».")
        vistas.add(s["clave"])
        if s.get("contenido", "NINGUNO") not in contenidos:
            raise ErrorConfiguracion(f"{donde}: «contenido» no válido: {s.get('contenido')}.")
    return secciones


def _parametros_propuestos(demo: bool) -> dict[str, Any]:
    datos = _leer("memoria.yaml", directorio_config(demo))
    p = datos.get("parametros") or {}
    if not isinstance(p, dict):
        raise ErrorConfiguracion("memoria.yaml: «parametros» debe ser un diccionario.")
    return p


# ------------------------------------------------------------------------ siembra


@transaction.atomic
def asegurar_configuracion(demo: bool = False) -> None:
    """Crea lo que falte con los valores propuestos. No toca nada de lo ya existente."""
    for orden, s in enumerate(secciones_propuestas(), start=1):
        SeccionMemoriaCfg.objects.get_or_create(
            clave=s["clave"],
            es_demo=demo,
            defaults={
                "titulo": s["titulo"],
                "orden": orden,
                "contenido": s.get("contenido", "NINGUNO"),
                "obligatoria": bool(s.get("obligatoria", True)),
                "solo_con_proceso_electoral": bool(s.get("solo_con_proceso_electoral", False)),
                "longitud_minima": s.get("longitud_minima"),
                "ayuda": (s.get("ayuda") or "").strip(),
                "plantilla": (s.get("plantilla") or "").rstrip(),
            },
        )
    if ParametrosAnexosCfg.objects.filter(es_demo=demo).exists():
        return
    p = _parametros_propuestos(demo)
    ingresos = p.get("reduccion_ingresos_prudente") or {}
    gastos = p.get("reduccion_gastos_ajustado") or {}
    valores: dict[str, Any] = {
        "variaciones_destacadas": int(p.get("variaciones_destacadas", 5)),
        "saldo_minimo_tesoreria": _decimal(
            p.get("saldo_minimo_tesoreria"), "saldo_minimo_tesoreria"
        ),
    }
    for campo in (
        "porcentaje_aviso_limite_campana",
        "semaforo_ambar_pct",
        "semaforo_rojo_pct",
        "semaforo_importe_minimo",
    ):
        valores[campo] = _decimal(p.get(campo), campo)
    if p.get("marcas_pendiente"):
        valores["marcas_pendiente"] = "\n".join(str(m) for m in p["marcas_pendiente"])
    for confianza, campo in CAMPOS_CONFIANZA.items():
        valores[campo] = _decimal(ingresos.get(confianza.value), campo)
    for tipo, campo in CAMPOS_TIPO.items():
        valores[campo] = _decimal(gastos.get(tipo.value), campo)
    ParametrosAnexosCfg.objects.create(es_demo=demo, **valores)


# --------------------------------------------------------------------- lectura actual


def parametros_actuales(demo: bool = False) -> ParametrosAnexos:
    """Configuración vigente ahora mismo (la que se usa para los borradores)."""
    asegurar_configuracion(demo)
    p = ParametrosAnexosCfg.objects.get(es_demo=demo)
    secciones = tuple(
        SeccionCfg(
            clave=s.clave,
            titulo=s.titulo,
            orden=s.orden,
            contenido=s.contenido,
            obligatoria=s.obligatoria,
            solo_con_proceso_electoral=s.solo_con_proceso_electoral,
            longitud_minima=s.longitud_minima,
            ayuda=s.ayuda,
            plantilla=s.plantilla,
        )
        for s in SeccionMemoriaCfg.objects.filter(es_demo=demo, activa=True)
    )
    return ParametrosAnexos(
        secciones=secciones,
        marcas_pendiente=tuple(p.marcas),
        variaciones_destacadas=p.variaciones_destacadas,
        saldo_minimo=p.saldo_minimo_tesoreria,
        reduccion_ingresos={c.value: getattr(p, campo) for c, campo in CAMPOS_CONFIANZA.items()},
        reduccion_gastos={t.value: getattr(p, campo) for t, campo in CAMPOS_TIPO.items()},
        porcentaje_aviso_limite_campana=p.porcentaje_aviso_limite_campana,
        semaforo_ambar_pct=p.semaforo_ambar_pct,
        semaforo_rojo_pct=p.semaforo_rojo_pct,
        semaforo_importe_minimo=p.semaforo_importe_minimo,
    )


def parametros_de_version(version: VersionPresupuesto) -> ParametrosAnexos:
    """Los parámetros con los que se SELLÓ la versión; si es borrador (o antigua), los actuales."""
    if version.estado != "BORRADOR":
        from apps.flujo.models import TransicionEstado

        t = (
            TransicionEstado.objects.filter(version=version, a_estado="PROPUESTO")
            .order_by("-id")
            .first()
        )
        guardados = (t.validacion or {}).get("parametros_anexos") if t else None
        if guardados:
            return ParametrosAnexos.desde_json(guardados)
    return parametros_actuales(version.es_demo)
