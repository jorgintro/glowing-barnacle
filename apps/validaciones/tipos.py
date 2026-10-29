"""Tipos comunes del motor de validaciones (CLAUDE.md §8)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class Gravedad(StrEnum):
    BLOQUEANTE = "BLOQUEANTE"  # impide avanzar de estado
    AVISO = "AVISO"  # se muestra y requiere constancia


@dataclass(frozen=True)
class Incidencia:
    codigo: str
    gravedad: Gravedad
    mensaje: str
    linea: str | None = None  # código de la línea afectada, si procede


@dataclass(frozen=True)
class Regla:
    codigo: str
    titulo: str
    gravedad: Gravedad
    fuente: str
    funcion: Callable[..., list[Incidencia]]


@dataclass
class ResultadoValidacion:
    incidencias: list[Incidencia] = field(default_factory=list)
    reglas_ejecutadas: list[str] = field(default_factory=list)

    @property
    def bloqueantes(self) -> list[Incidencia]:
        return [i for i in self.incidencias if i.gravedad == Gravedad.BLOQUEANTE]

    @property
    def avisos(self) -> list[Incidencia]:
        return [i for i in self.incidencias if i.gravedad == Gravedad.AVISO]

    @property
    def puede_avanzar(self) -> bool:
        return not self.bloqueantes

    def codigos_incumplidos(self) -> set[str]:
        return {i.codigo for i in self.incidencias}

    def superadas(self) -> list[str]:
        """Reglas ejecutadas sin ninguna incidencia (para el checklist de cumplimiento)."""
        malas = self.codigos_incumplidos()
        return [c for c in self.reglas_ejecutadas if c not in malas]
