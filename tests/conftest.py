import pytest
from django.test import Client

from apps.auditoria.servicios import Contexto
from apps.usuarios import servicios
from apps.usuarios.models import Usuario
from apps.usuarios.roles import Rol

CLAVE = "clave-de-prueba-larga-1"


def crear(username: str, *roles: str, **extra: object) -> Usuario:
    """Crea un usuario saltándose el permiso (solo para montar escenarios de prueba)."""
    base = Usuario.objects.create_user(username, password=CLAVE, **extra)  # type: ignore[arg-type]
    from apps.usuarios.models import AsignacionRol

    for rol in roles:
        AsignacionRol.objects.create(usuario=base, rol=rol)
    return base


@pytest.fixture
def tesorero(db: None) -> Usuario:
    return crear("tesorera", Rol.TESORERO, first_name="Tesorera", last_name="Ficticia")


@pytest.fixture
def ctx_tesorero(tesorero: Usuario) -> Contexto:
    return Contexto(tesorero, Rol.TESORERO, "127.0.0.1")


@pytest.fixture
def cliente_tesorero(tesorero: Usuario) -> Client:
    c = Client()
    assert c.login(username="tesorera", password=CLAVE)
    return c


__all__ = ["CLAVE", "crear", "servicios"]


@pytest.fixture
def catalogo(db: None) -> None:
    from apps.presupuesto.sincronizacion import (
        sincronizar_cuadro_cuentas,
        sincronizar_parametros_legales,
    )

    sincronizar_cuadro_cuentas()
    sincronizar_parametros_legales()


@pytest.fixture
def borrador(catalogo: None, ctx_tesorero: Contexto):
    from apps.presupuesto import servicios as ps

    _, version = ps.crear_ejercicio(ctx_tesorero, anio=2040, nombre="Ejercicio de prueba")
    return version
