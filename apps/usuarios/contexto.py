from django.http import HttpRequest

from .roles import Rol


def rol_activo(request: HttpRequest) -> dict[str, object]:
    activo = getattr(request, "rol_activo", None)
    return {
        "rol_activo": activo,
        "rol_activo_nombre": Rol(activo).label if activo else "",
        "es_tesorero": activo == Rol.TESORERO,
    }
