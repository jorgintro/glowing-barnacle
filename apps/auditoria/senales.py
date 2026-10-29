"""Registro de accesos (§13.2): entradas, salidas e intentos fallidos."""

from typing import Any

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.http import HttpRequest

from .servicios import Contexto, registrar


def _ip(request: HttpRequest | None) -> str | None:
    return request.META.get("REMOTE_ADDR") if request is not None else None


@receiver(user_logged_in)
def registrar_entrada(sender: Any, request: HttpRequest, user: Any, **kwargs: Any) -> None:
    registrar(
        Contexto(user, "", _ip(request)),
        accion="acceso.entrada",
        entidad="Usuario",
        entidad_id=user.pk,
    )


@receiver(user_logged_out)
def registrar_salida(sender: Any, request: HttpRequest, user: Any, **kwargs: Any) -> None:
    if user is not None:
        registrar(
            Contexto(user, "", _ip(request)),
            accion="acceso.salida",
            entidad="Usuario",
            entidad_id=user.pk,
        )


@receiver(user_login_failed)
def registrar_fallo(
    sender: Any, credentials: dict[str, Any], request: HttpRequest | None = None, **kwargs: Any
) -> None:
    registrar(
        Contexto(None, "", _ip(request)),
        accion="acceso.fallido",
        entidad="Usuario",
        usuario_texto=str(credentials.get("username", ""))[:150],
    )
