"""Punto único de entrada para dejar constancia de una acción."""

from dataclasses import dataclass
from typing import Any

from django.http import HttpRequest

from .models import RegistroAuditoria


@dataclass(frozen=True)
class Contexto:
    """Quién actúa, con qué rol y desde dónde."""

    usuario: Any  # Usuario autenticado o None
    rol_activo: str = ""
    ip: str | None = None

    @classmethod
    def desde_request(cls, request: HttpRequest) -> "Contexto":
        usuario = request.user if request.user.is_authenticated else None
        return cls(
            usuario=usuario,
            rol_activo=getattr(request, "rol_activo", None) or "",
            ip=request.META.get("REMOTE_ADDR") or None,
        )


def registrar(
    contexto: Contexto,
    *,
    accion: str,
    entidad: str,
    entidad_id: object = "",
    antes: object = None,
    despues: object = None,
    motivo: str = "",
    usuario_texto: str = "",
    es_demo: bool = False,
) -> RegistroAuditoria:
    usuario = contexto.usuario
    es_demo = es_demo or bool(getattr(usuario, "es_demo", False))
    return RegistroAuditoria.objects.create(
        usuario=usuario,
        usuario_texto=usuario_texto or (usuario.get_username() if usuario else ""),
        rol_activo=contexto.rol_activo,
        accion=accion,
        entidad=entidad,
        entidad_id=str(entidad_id),
        antes=antes,
        despues=despues,
        motivo=motivo,
        ip=contexto.ip,
        es_demo=es_demo,
    )
