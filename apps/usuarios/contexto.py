from django.http import HttpRequest

from .roles import Rol


def rol_activo(request: HttpRequest) -> dict[str, object]:
    activo = getattr(request, "rol_activo", None)
    nombre = Rol(activo).label if activo else ""
    if activo == Rol.TESORERO:
        # La organización puede llamar «Gerente» (u otro nombre) al cargo de Tesorería.
        from apps.organizacion.models import Organizacion

        denominacion = (
            Organizacion.objects.filter(pk=1)
            .values_list("denominacion_tesoreria", flat=True)
            .first()
        )
        nombre = denominacion or nombre
    return {
        "rol_activo": activo,
        "rol_activo_nombre": nombre,
        "es_tesorero": activo == Rol.TESORERO,
    }
