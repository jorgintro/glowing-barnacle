"""Lectura y validación de los ficheros de ``config/`` (CLAUDE.md §3 y §9.4).

Los límites legales no están en el código: se leen de aquí. Si un fichero está mal formado,
se falla con un mensaje claro en lugar de seguir con datos dudosos.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings

UNIDADES_VALIDAS = {"EUR", "PORCENTAJE", "BOOLEANO", "LISTA", "TEXTO"}
DIMENSIONES_VALIDAS = {"ORDINARIO", "CAMPANA", "GRUPO_MUNICIPAL"}
TIPOS_VALIDOS = {"INGRESO", "GASTO"}


class ErrorConfiguracion(Exception):
    """Un fichero de configuración está mal formado."""


@dataclass(frozen=True)
class CuentaCfg:
    codigo: str
    denominacion: str


@dataclass(frozen=True)
class PartidaCfg:
    codigo: str
    denominacion: str
    cuentas: tuple[str, ...]
    dimension: str


@dataclass(frozen=True)
class CapituloCfg:
    codigo: str
    tipo: str
    denominacion: str
    solo_con_proceso_electoral: bool
    partidas: tuple[PartidaCfg, ...]


@dataclass(frozen=True)
class CuadroCuentasCfg:
    validado_por: str | None
    fecha_validacion: date | None
    cuentas: tuple[CuentaCfg, ...]
    capitulos: tuple[CapituloCfg, ...]

    @property
    def validado(self) -> bool:
        return bool(self.validado_por) and self.fecha_validacion is not None


@dataclass(frozen=True)
class ParametroCfg:
    clave: str
    descripcion: str
    unidad: str
    regla: str
    norma_orientativa: str
    valor: Any
    referencia_normativa: str
    fecha_verificacion: date | None
    verificador: str


@dataclass(frozen=True)
class ParametrosLegalesCfg:
    parametros: tuple[ParametroCfg, ...] = field(default_factory=tuple)


def _leer(nombre: str, directorio: Path | None = None) -> dict[str, Any]:
    ruta = (directorio or Path(settings.CONFIG_DIR)) / nombre
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


def _texto(valor: object, donde: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorConfiguracion(f"{donde}: falta un texto obligatorio.")
    return valor.strip()


def _fecha(valor: object, donde: str) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, date):
        return valor
    raise ErrorConfiguracion(f"{donde}: la fecha debe escribirse AAAA-MM-DD.")


def cargar_cuadro_cuentas(directorio: Path | None = None) -> CuadroCuentasCfg:
    datos = _leer("cuadro_cuentas.yaml", directorio)
    cuentas: list[CuentaCfg] = []
    for c in datos.get("cuentas") or []:
        cuentas.append(
            CuentaCfg(_texto(c.get("codigo"), "cuenta"), _texto(c.get("denominacion"), "cuenta"))
        )
    codigos = [c.codigo for c in cuentas]
    if len(set(codigos)) != len(codigos):
        raise ErrorConfiguracion("cuadro_cuentas.yaml: hay cuentas con código repetido.")

    capitulos: list[CapituloCfg] = []
    vistos: set[str] = set()
    for cap in datos.get("capitulos") or []:
        cod_cap = _texto(cap.get("codigo"), "capítulo")
        tipo = cap.get("tipo")
        if tipo not in TIPOS_VALIDOS:
            raise ErrorConfiguracion(f"Capítulo {cod_cap}: tipo debe ser INGRESO o GASTO.")
        partidas: list[PartidaCfg] = []
        for p in cap.get("partidas") or []:
            cod_p = _texto(p.get("codigo"), f"partida de {cod_cap}")
            if not cod_p.startswith(cod_cap + "."):
                raise ErrorConfiguracion(f"Partida {cod_p}: debe empezar por {cod_cap}.")
            usadas = tuple(str(x) for x in (p.get("cuentas") or []))
            if not usadas:
                raise ErrorConfiguracion(f"Partida {cod_p}: debe tener al menos una cuenta.")
            desconocidas = [x for x in usadas if x not in codigos]
            if desconocidas:
                raise ErrorConfiguracion(f"Partida {cod_p}: cuentas no definidas {desconocidas}.")
            dimension = p.get("dimension", "ORDINARIO")
            if dimension not in DIMENSIONES_VALIDAS:
                raise ErrorConfiguracion(f"Partida {cod_p}: dimensión desconocida «{dimension}».")
            partidas.append(
                PartidaCfg(cod_p, _texto(p.get("denominacion"), cod_p), usadas, dimension)
            )
        if not partidas:
            raise ErrorConfiguracion(f"Capítulo {cod_cap}: no tiene partidas.")
        for x in [cod_cap, *[p.codigo for p in partidas]]:
            if x in vistos:
                raise ErrorConfiguracion(f"Código repetido: {x}.")
            vistos.add(x)
        capitulos.append(
            CapituloCfg(
                cod_cap,
                tipo,
                _texto(cap.get("denominacion"), cod_cap),
                bool(cap.get("solo_con_proceso_electoral", False)),
                tuple(partidas),
            )
        )
    if not capitulos:
        raise ErrorConfiguracion("cuadro_cuentas.yaml: no hay capítulos.")
    return CuadroCuentasCfg(
        validado_por=datos.get("validado_por") or None,
        fecha_validacion=_fecha(datos.get("fecha_validacion"), "fecha_validacion"),
        cuentas=tuple(cuentas),
        capitulos=tuple(capitulos),
    )


def cargar_parametros_legales(directorio: Path | None = None) -> ParametrosLegalesCfg:
    datos = _leer("parametros_legales.yaml", directorio)
    resultado: list[ParametroCfg] = []
    for p in datos.get("parametros") or []:
        clave = _texto(p.get("clave"), "parámetro")
        if any(r.clave == clave for r in resultado):
            raise ErrorConfiguracion(f"Parámetro repetido: {clave}.")
        unidad = p.get("unidad")
        if unidad not in UNIDADES_VALIDAS:
            raise ErrorConfiguracion(f"Parámetro {clave}: unidad desconocida «{unidad}».")
        valor = p.get("valor")
        if isinstance(valor, float):
            raise ErrorConfiguracion(
                f"Parámetro {clave}: los importes se escriben como texto entre comillas, "
                'p. ej. "1234.56" (nunca como número decimal).'
            )
        resultado.append(
            ParametroCfg(
                clave=clave,
                descripcion=_texto(p.get("descripcion"), clave),
                unidad=unidad,
                regla=str(p.get("regla") or ""),
                norma_orientativa=str(p.get("norma_orientativa") or ""),
                valor=valor,
                referencia_normativa=str(p.get("referencia_normativa") or ""),
                fecha_verificacion=_fecha(p.get("fecha_verificacion"), clave),
                verificador=str(p.get("verificador") or ""),
            )
        )
    return ParametrosLegalesCfg(tuple(resultado))
