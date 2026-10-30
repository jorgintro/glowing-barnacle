"""Sellado de versiones: huella (SHA-256) del contenido y cadena de transiciones.

La huella cubre todo el contenido que importa: ejercicio, versión, líneas, hipótesis, importes
mensuales y donaciones. Desde la huella de tipo 2 cubre además la memoria explicativa y el saldo
inicial de tesorería y, desde la de tipo 3, los datos del proceso electoral; las versiones selladas
antes se siguen verificando con su tipo.
Se calcula con una representación canónica (claves y listas ordenadas, importes como texto),
así que no cambia por el orden en que se guardaron los datos.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from apps.presupuesto.models import Donacion, ImporteMensual, Linea, VersionPresupuesto

from .models import TransicionEstado

HUELLA_ACTUAL = 3


def contenido_canonico(version: VersionPresupuesto) -> dict[str, Any]:
    lineas = []
    for ln in (
        Linea.objects.filter(version=version)
        .select_related("partida", "cuenta_pgc", "hipotesis")
        .order_by("codigo")
    ):
        h = getattr(ln, "hipotesis", None)
        lineas.append(
            {
                "codigo": ln.codigo,
                "partida": ln.partida.codigo,
                "denominacion": ln.denominacion,
                "cuenta": ln.cuenta_pgc.codigo if ln.cuenta_pgc else None,
                "importe_anual": str(ln.importe_anual),
                "mensual": [
                    str(m.importe) for m in ImporteMensual.objects.filter(linea=ln).order_by("mes")
                ],
                "tipo": ln.tipo,
                "dimension": ln.dimension,
                "anterior": None
                if ln.importe_ejercicio_anterior is None
                else str(ln.importe_ejercicio_anterior),
                "justificacion_variacion": ln.justificacion_variacion,
                "responsable": ln.responsable,
                "origen_ingreso": ln.origen_ingreso,
                "operaciones_altas": None
                if ln.operaciones_altas is None
                else str(ln.operaciones_altas),
                "es_ajuste": ln.es_ajuste,
                "justificacion_ajuste": ln.justificacion_ajuste,
                "anulada": ln.anulada,
                "motivo_anulacion": ln.motivo_anulacion,
                "hipotesis": None
                if h is None
                else {"texto": h.texto, "fuente": h.fuente, "confianza": h.confianza},
            }
        )
    donaciones = sorted(
        (
            {
                "linea": d.linea.codigo,
                "donante": d.donante.nif,
                "tipo_persona": d.donante.tipo_persona,
                "contratista_publico": d.donante.contratista_publico,
                "importe": str(d.importe),
                "tipo": d.tipo,
                "finalista": d.finalista,
                "revocable": d.revocable,
                "anulada": d.anulada,
            }
            for d in Donacion.objects.filter(version=version).select_related("linea", "donante")
        ),
        key=lambda x: (x["linea"], x["donante"], x["importe"], x["tipo"]),
    )
    contenido = _contenido_base(version, lineas, donaciones)
    if version.version_huella >= 2:
        from apps.anexos.models import SeccionMemoria

        contenido["memoria"] = {
            s.clave: s.texto
            for s in SeccionMemoria.objects.filter(version=version).order_by("clave")
        }
        saldo = version.saldo_inicial_tesoreria
        contenido["tesoreria"] = {"saldo_inicial": None if saldo is None else str(saldo)}
    if version.version_huella >= 3:
        contenido["campana"] = _proceso_electoral_canonico(version)
    return contenido


def _proceso_electoral_canonico(version: VersionPresupuesto) -> dict[str, Any] | None:
    from apps.anexos.models import ProcesoElectoral

    pe = ProcesoElectoral.objects.filter(version=version).first()
    if pe is None:
        return None

    def f(valor: Any) -> str | None:
        return None if valor is None else str(valor)

    return {
        "denominacion": pe.denominacion,
        "fecha_convocatoria": f(pe.fecha_convocatoria),
        "fecha_elecciones": f(pe.fecha_elecciones),
        "fecha_proclamacion": f(pe.fecha_proclamacion),
        "habitantes_derecho": pe.habitantes_derecho,
        "provincias_adicional": pe.provincias_adicional,
        "subvencion_envio_aplicable": pe.subvencion_envio_aplicable,
        "electores_envio": pe.electores_envio,
        "concejales_previstos": pe.concejales_previstos,
        "votos_previstos": pe.votos_previstos,
        "observaciones": pe.observaciones,
    }


def _contenido_base(
    version: VersionPresupuesto, lineas: list[dict[str, Any]], donaciones: list[dict[str, Any]]
) -> dict[str, Any]:
    ej = version.ejercicio
    contenido = _contenido_base_sin_ambito(version, lineas, donaciones, ej)
    if version.ambito != "ORDINARIO":  # las huellas de los presupuestos ordinarios no cambian
        contenido["version"]["ambito"] = version.ambito
    return contenido


def _contenido_base_sin_ambito(
    version: VersionPresupuesto,
    lineas: list[dict[str, Any]],
    donaciones: list[dict[str, Any]],
    ej: Any,
) -> dict[str, Any]:
    return {
        "ejercicio": {"anio": ej.anio, "proceso_electoral": ej.hay_proceso_electoral},
        "version": {
            "numero": version.numero,
            "motivo": version.motivo,
            "origen": version.version_origen.numero if version.version_origen else None,
            "tipo_origen": version.tipo_origen,
            "es_prorroga": version.es_prorroga,
            "explicacion_resultado": version.explicacion_resultado,
            "plan_financiacion": version.plan_financiacion,
            "endeudamiento_previsto": str(version.endeudamiento_previsto),
        },
        "lineas": lineas,
        "donaciones": donaciones,
    }


def calcular_hash(version: VersionPresupuesto) -> str:
    texto = json.dumps(
        contenido_canonico(version), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def iso_utc(fecha: datetime) -> str:
    """Fecha en UTC con microsegundos: la misma cadena al crear y al leer de la base de datos."""
    return fecha.astimezone(UTC).isoformat()


def hash_encadenado(
    *,
    hash_previo: str,
    hash_version: str,
    de_estado: str,
    a_estado: str,
    usuario_id: int | None,
    fecha_iso: str,
    motivo: str,
) -> str:
    partes = [hash_previo, hash_version, de_estado, a_estado, str(usuario_id), fecha_iso, motivo]
    return hashlib.sha256("\x1f".join(partes).encode("utf-8")).hexdigest()


@dataclass
class ResultadoIntegridad:
    version: VersionPresupuesto
    problemas: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problemas


def verificar_integridad(version: VersionPresupuesto) -> ResultadoIntegridad:
    """Recalcula la huella del contenido y revisa la cadena de transiciones."""
    res = ResultadoIntegridad(version)
    if version.estado != "BORRADOR":
        if not version.hash:
            res.problemas.append("La versión no tiene huella.")
        elif calcular_hash(version) != version.hash:
            res.problemas.append(
                "El contenido de la versión NO coincide con su huella: alguien lo ha modificado."
            )
    previo = ""
    for t in TransicionEstado.objects.filter(version=version).order_by("id"):
        esperado = hash_encadenado(
            hash_previo=previo,
            hash_version=t.hash_version,
            de_estado=t.de_estado,
            a_estado=t.a_estado,
            usuario_id=t.usuario_id,
            fecha_iso=iso_utc(t.fecha),
            motivo=t.motivo,
        )
        if t.hash_previo != previo or t.hash_encadenado != esperado:
            res.problemas.append(
                f"La transición {t.de_estado} → {t.a_estado} (nº {t.pk}) no encaja en la cadena."
            )
        previo = t.hash_encadenado
    return res
