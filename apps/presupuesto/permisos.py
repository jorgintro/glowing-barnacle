"""Quién puede ver qué versión (CLAUDE.md §4).

* Tesorero: todas.
* Comisión Permanente: todas menos los borradores (aún no le han sido propuestos).
* Junta General: solo lo ya aprobado por la Comisión Permanente o ratificado.
"""

from django.db.models import QuerySet

from apps.usuarios.roles import Rol

from .estados import EstadoVersion
from .models import VersionPresupuesto

_VISIBLES_CP = [e for e in EstadoVersion if e != EstadoVersion.BORRADOR]
_VISIBLES_JG = [EstadoVersion.APROBADO_CP, EstadoVersion.RATIFICADO_JG, EstadoVersion.MODIFICADO]


def versiones_visibles(rol: str | None) -> QuerySet[VersionPresupuesto]:
    base = VersionPresupuesto.objects.select_related("ejercicio")
    if rol == Rol.TESORERO:
        return base
    if rol == Rol.COMISION_PERMANENTE:
        return base.filter(estado__in=_VISIBLES_CP)
    if rol == Rol.JUNTA_GENERAL:
        return base.filter(estado__in=_VISIBLES_JG)
    return base.none()
