"""Un usuario, un rol activo por sesión (§4)."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

CLAVE_SESION = "rol_activo"


class RolActivoMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.rol_activo = None  # type: ignore[attr-defined]
        if request.user.is_authenticated:
            asignados = request.user.roles_vigentes()
            rol = request.session.get(CLAVE_SESION)
            if rol not in asignados:  # rol retirado o sesión antigua
                request.session.pop(CLAVE_SESION, None)
                rol = None
            if rol is None and len(asignados) == 1:
                rol = asignados[0]
                request.session[CLAVE_SESION] = rol
            request.rol_activo = rol  # type: ignore[attr-defined]
            if rol is None and not self._exenta(request):
                return redirect("usuarios:seleccionar_rol")
        return self.get_response(request)

    @staticmethod
    def _exenta(request: HttpRequest) -> bool:
        return request.path in {reverse("usuarios:seleccionar_rol"), reverse("usuarios:salir")} or (
            request.path.startswith("/static/")
        )
