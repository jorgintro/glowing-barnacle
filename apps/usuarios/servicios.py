"""Gestión de usuarios y roles. Solo el Tesorero cambia roles y todo queda registrado (§4)."""

from collections.abc import Iterable

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.servicios import Contexto, registrar

from .models import AsignacionRol, Usuario
from .roles import Rol


def _exigir_tesorero(contexto: Contexto) -> None:
    if contexto.usuario is None or contexto.rol_activo != Rol.TESORERO:
        raise PermissionDenied("Solo el Tesorero puede gestionar usuarios y roles.")


def _tesoreros_vigentes() -> set[int]:
    return set(
        AsignacionRol.objects.filter(
            rol=Rol.TESORERO, fecha_fin__isnull=True, usuario__is_active=True
        ).values_list("usuario_id", flat=True)
    )


def _roles_validos(roles: Iterable[str]) -> set[str]:
    validos = {r.value for r in Rol}
    pedidos = set(roles)
    if not pedidos <= validos:
        raise ValidationError("Rol desconocido.")
    return pedidos


@transaction.atomic
def crear_usuario(
    contexto: Contexto,
    *,
    username: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    roles: Iterable[str] = (),
    es_demo: bool = False,
) -> Usuario:
    _exigir_tesorero(contexto)
    pedidos = _roles_validos(roles)
    usuario = Usuario(
        username=username, first_name=first_name, last_name=last_name, email=email, es_demo=es_demo
    )
    usuario.set_password(password)
    usuario.save()
    for rol in sorted(pedidos):
        AsignacionRol.objects.create(usuario=usuario, rol=rol, asignado_por=contexto.usuario)
    registrar(
        contexto,
        accion="usuario.crear",
        entidad="Usuario",
        entidad_id=usuario.pk,
        despues={"username": username, "roles": sorted(pedidos)},
        es_demo=es_demo,
    )
    return usuario


@transaction.atomic
def actualizar_roles(
    contexto: Contexto, usuario: Usuario, roles_nuevos: Iterable[str], motivo: str = ""
) -> None:
    """Deja al usuario con exactamente ``roles_nuevos``. Retirar un rol exige motivo."""
    _exigir_tesorero(contexto)
    nuevos = _roles_validos(roles_nuevos)
    actuales = set(usuario.roles_vigentes())
    a_retirar, a_anadir = actuales - nuevos, nuevos - actuales
    if not a_retirar and not a_anadir:
        return
    if a_retirar and not motivo.strip():
        raise ValidationError("Para retirar un rol hay que indicar el motivo.")
    if Rol.TESORERO in a_retirar and not (_tesoreros_vigentes() - {usuario.pk}):
        raise ValidationError("Debe quedar al menos un Tesorero activo en el sistema.")

    ahora = timezone.now()
    AsignacionRol.objects.filter(usuario=usuario, rol__in=a_retirar, fecha_fin__isnull=True).update(
        fecha_fin=ahora, motivo_fin=motivo
    )
    for rol in sorted(a_anadir):
        AsignacionRol.objects.create(usuario=usuario, rol=rol, asignado_por=contexto.usuario)
    registrar(
        contexto,
        accion="usuario.cambiar_roles",
        entidad="Usuario",
        entidad_id=usuario.pk,
        antes={"roles": sorted(actuales)},
        despues={"roles": sorted(nuevos)},
        motivo=motivo,
        es_demo=usuario.es_demo,
    )


@transaction.atomic
def dar_de_baja(contexto: Contexto, usuario: Usuario, motivo: str) -> None:
    _exigir_tesorero(contexto)
    if not motivo.strip():
        raise ValidationError("Para dar de baja a un usuario hay que indicar el motivo.")
    if not usuario.is_active:
        return
    if usuario.pk in _tesoreros_vigentes() and not (_tesoreros_vigentes() - {usuario.pk}):
        raise ValidationError("Debe quedar al menos un Tesorero activo en el sistema.")
    usuario.is_active = False
    usuario.fecha_baja = timezone.now()
    usuario.save(update_fields=["is_active", "fecha_baja"])
    registrar(
        contexto,
        accion="usuario.baja",
        entidad="Usuario",
        entidad_id=usuario.pk,
        antes={"activo": True},
        despues={"activo": False},
        motivo=motivo,
        es_demo=usuario.es_demo,
    )
