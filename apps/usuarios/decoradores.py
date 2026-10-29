from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

Vista = Callable[..., HttpResponse]


def requiere_rol(*roles: str) -> Callable[[Vista], Vista]:
    """Exige sesión iniciada y que el rol activo sea uno de ``roles``."""

    def decorador(vista: Vista) -> Vista:
        @wraps(vista)
        @login_required
        def envoltura(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if getattr(request, "rol_activo", None) not in roles:
                return render(request, "403.html", status=403)
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
