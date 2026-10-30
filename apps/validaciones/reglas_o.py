"""Validaciones orgánicas (CLAUDE.md §8.3).

Son funciones puras sobre datos simples: en la Fase 4 el flujo les pasará los datos de la
votación y la ratificación. Aritmética entera (sin ``float``).
"""

from dataclasses import dataclass, field
from datetime import date

from apps.presupuesto.configuracion import Fraccion, ReglasOrganicasCfg

from .tipos import Gravedad, Incidencia

RESULTADOS_RATIFICACION = {"RATIFICADO", "RECHAZADO"}


@dataclass(frozen=True)
class DatosVotacion:
    miembros: int  # miembros de la Comisión Permanente con derecho a voto
    asistentes: int
    a_favor: int
    en_contra: int
    abstenciones: int
    proponente: int | None = None  # id del usuario que propone
    votantes: tuple[int, ...] = field(default_factory=tuple)  # ids de quienes han votado


@dataclass(frozen=True)
class DatosRatificacion:
    fecha: date | None
    resultado: str
    referencia_acta: str
    fecha_aprobacion_cp: date | None = None
    fecha_convocatoria: date | None = None


def _alcanza(valor: int, base: int, f: Fraccion) -> bool:
    """¿``valor/base`` alcanza (o supera, si es estricto) la fracción?  Sin decimales."""
    izquierda, derecha = valor * f.denominador, f.numerador * base
    return izquierda > derecha if f.estricto else izquierda >= derecha


def _inc(codigo: str, msg: str, g: Gravedad = Gravedad.BLOQUEANTE) -> Incidencia:
    return Incidencia(codigo, g, msg)


@dataclass(frozen=True)
class EvaluacionVotacion:
    """Resultado detallado de O-001: el flujo necesita saber qué falla (quórum o mayoría)."""

    configurada: bool
    coherente: bool
    quorum: bool
    mayoria: bool
    incidencias: tuple[Incidencia, ...]

    @property
    def aprobada(self) -> bool:
        return self.configurada and self.coherente and self.quorum and self.mayoria


def evaluar_votacion(votacion: DatosVotacion, cfg: ReglasOrganicasCfg) -> EvaluacionVotacion:
    if cfg.quorum is None or cfg.mayoria is None:
        aviso = _inc(
            "O-001",
            "Quórum y mayoría sin configurar (config/reglas_organicas.yaml): la votación "
            "queda bloqueada hasta que se rellenen según los estatutos.",
        )
        return EvaluacionVotacion(False, True, False, False, (aviso,))
    v = votacion
    emitidos = v.a_favor + v.en_contra + v.abstenciones
    if min(v.miembros, v.asistentes, v.a_favor, v.en_contra, v.abstenciones) < 0:
        malo = _inc("O-001", "Los recuentos no pueden ser negativos.")
        return EvaluacionVotacion(True, False, False, False, (malo,))
    if v.miembros == 0:
        malo = _inc("O-001", "No hay miembros de la Comisión Permanente con derecho a voto.")
        return EvaluacionVotacion(True, False, False, False, (malo,))
    incoherencias = []
    if v.asistentes > v.miembros:
        incoherencias.append(_inc("O-001", "Hay más asistentes que miembros."))
    if emitidos > v.asistentes:
        incoherencias.append(_inc("O-001", "Hay más votos emitidos que asistentes."))
    if incoherencias:
        return EvaluacionVotacion(True, False, False, False, tuple(incoherencias))

    incidencias = []
    quorum = _alcanza(v.asistentes, v.miembros, cfg.quorum)
    if not quorum:
        incidencias.append(
            _inc("O-001", f"No hay quórum: asisten {v.asistentes} de {v.miembros} miembros.")
        )
    m = cfg.mayoria
    if m.tipo == "SIMPLE":
        mayoria = v.a_favor > v.en_contra
        if not mayoria:
            incidencias.append(
                _inc(
                    "O-001",
                    f"No hay mayoría simple: {v.a_favor} a favor y {v.en_contra} en contra.",
                )
            )
    else:
        assert m.fraccion is not None and m.base is not None
        base = {
            "MIEMBROS": v.miembros,
            "ASISTENTES": v.asistentes,
            "EMITIDOS": emitidos,
            "EMITIDOS_SIN_ABSTENCIONES": v.a_favor + v.en_contra,
        }[m.base]
        mayoria = base != 0 and _alcanza(v.a_favor, base, m.fraccion)
        if not mayoria:
            incidencias.append(
                _inc(
                    "O-001",
                    f"No se alcanza la mayoría exigida: {v.a_favor} votos a favor sobre una "
                    f"base de {base}.",
                )
            )
    return EvaluacionVotacion(True, True, quorum, mayoria, tuple(incidencias))


def o001(votacion: DatosVotacion, cfg: ReglasOrganicasCfg) -> list[Incidencia]:
    """La Comisión Permanente alcanza quórum y mayoría según los estatutos."""
    return list(evaluar_votacion(votacion, cfg).incidencias)


def o002(r: DatosRatificacion, hoy: date) -> list[Incidencia]:
    """La ratificación se registra con fecha, resultado y referencia al acta."""
    salida = []
    if r.fecha is None:
        salida.append(_inc("O-002", "Falta la fecha de la sesión de la Junta."))
    else:
        if r.fecha > hoy:
            salida.append(_inc("O-002", "La fecha de la sesión es futura."))
        if r.fecha_aprobacion_cp is not None and r.fecha < r.fecha_aprobacion_cp:
            salida.append(
                _inc("O-002", "La Junta no puede ratificar antes de la aprobación de la CP.")
            )
    if r.resultado not in RESULTADOS_RATIFICACION:
        salida.append(_inc("O-002", "El resultado debe ser RATIFICADO o RECHAZADO."))
    if not r.referencia_acta.strip():
        salida.append(_inc("O-002", "Falta la referencia al acta."))
    return salida


def o003(votacion: DatosVotacion, cfg: ReglasOrganicasCfg) -> list[Incidencia]:
    """Quien propone no vota en la CP en la misma versión si el reglamento lo impide.

    Si el reglamento no está configurado se aplica la opción prudente: no puede votar.
    """
    permitido = cfg.proponente_puede_votar is True
    if (
        not permitido
        and votacion.proponente is not None
        and votacion.proponente in votacion.votantes
    ):
        return [_inc("O-003", "Quien propone el presupuesto no puede votar su aprobación.")]
    return []


def o004(r: DatosRatificacion) -> list[Incidencia]:
    """Aviso: la convocatoria de la Junta se registró antes de la ratificación."""
    if r.fecha_convocatoria is None:
        return [_inc("O-004", "No consta la convocatoria de la Junta.", Gravedad.AVISO)]
    if r.fecha is not None and r.fecha_convocatoria > r.fecha:
        return [
            _inc("O-004", "La convocatoria es posterior a la sesión de la Junta.", Gravedad.AVISO)
        ]
    return []
