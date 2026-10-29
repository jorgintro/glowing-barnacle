import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.servicios import Contexto
from apps.usuarios import servicios
from apps.usuarios.roles import Rol
from tests.conftest import CLAVE, crear

pytestmark = pytest.mark.django_db


def test_login_con_un_solo_rol_lo_activa_solo() -> None:
    crear("unico", Rol.COMISION_PERMANENTE)
    c = Client()
    c.login(username="unico", password=CLAVE)
    r = c.get("/")
    assert r.status_code == 200
    assert r.context["rol_activo"] == Rol.COMISION_PERMANENTE


def test_con_varios_roles_obliga_a_elegir() -> None:
    crear("doble", Rol.TESORERO, Rol.COMISION_PERMANENTE)
    c = Client()
    c.login(username="doble", password=CLAVE)
    assert c.get("/").status_code == 302
    assert c.get("/")["Location"] == "/rol/"
    r = c.post("/rol/", {"rol": Rol.COMISION_PERMANENTE})
    assert r.status_code == 302
    assert c.get("/").context["rol_activo"] == Rol.COMISION_PERMANENTE
    assert RegistroAuditoria.objects.filter(accion="sesion.seleccionar_rol").exists()


def test_no_se_puede_elegir_un_rol_no_asignado() -> None:
    crear("solo_cp", Rol.COMISION_PERMANENTE)
    c = Client()
    c.login(username="solo_cp", password=CLAVE)
    c.post("/rol/", {"rol": Rol.TESORERO})
    assert c.get("/usuarios/").status_code == 403


def test_usuario_sin_roles_no_pasa_de_la_pantalla_de_rol() -> None:
    crear("sinroles")
    c = Client()
    c.login(username="sinroles", password=CLAVE)
    assert c.get("/")["Location"] == "/rol/"


def test_solo_el_tesorero_ve_la_gestion_de_usuarios() -> None:
    crear("cp", Rol.COMISION_PERMANENTE)
    c = Client()
    c.login(username="cp", password=CLAVE)
    assert c.get("/usuarios/").status_code == 403
    assert c.get("/usuarios/nuevo/").status_code == 403


def test_sin_sesion_redirige_a_entrar() -> None:
    r = Client().get("/usuarios/")
    assert r.status_code == 302 and r["Location"].startswith("/entrar/")


def test_rol_retirado_deja_de_valer_en_sesion_abierta(ctx_tesorero: Contexto) -> None:
    u = crear("temporal", Rol.TESORERO, Rol.COMISION_PERMANENTE)
    c = Client()
    c.login(username="temporal", password=CLAVE)
    c.post("/rol/", {"rol": Rol.TESORERO})
    assert c.get("/usuarios/").status_code == 200
    servicios.actualizar_roles(ctx_tesorero, u, [Rol.COMISION_PERMANENTE], "ya no es tesorero")
    assert c.get("/usuarios/").status_code in (302, 403)


def test_crear_usuario_queda_auditado(ctx_tesorero: Contexto) -> None:
    u = servicios.crear_usuario(
        ctx_tesorero, username="nuevo", password=CLAVE, roles=[Rol.COMISION_PERMANENTE]
    )
    assert u.roles_vigentes() == [Rol.COMISION_PERMANENTE]
    reg = RegistroAuditoria.objects.get(accion="usuario.crear")
    assert reg.despues == {"username": "nuevo", "roles": [Rol.COMISION_PERMANENTE]}
    assert reg.rol_activo == Rol.TESORERO


def test_otros_roles_no_pueden_gestionar_usuarios(tesorero: object) -> None:
    cp = crear("cp2", Rol.COMISION_PERMANENTE)
    ctx = Contexto(cp, Rol.COMISION_PERMANENTE)
    with pytest.raises(PermissionDenied):
        servicios.crear_usuario(ctx, username="x", password=CLAVE)
    with pytest.raises(PermissionDenied):
        servicios.actualizar_roles(ctx, cp, [Rol.TESORERO])


def test_cambio_de_roles_guarda_antes_y_despues(ctx_tesorero: Contexto) -> None:
    u = crear("cambia", Rol.COMISION_PERMANENTE)
    servicios.actualizar_roles(ctx_tesorero, u, [Rol.COMISION_PERMANENTE, Rol.JUNTA_GENERAL])
    reg = RegistroAuditoria.objects.get(accion="usuario.cambiar_roles")
    assert reg.antes == {"roles": [Rol.COMISION_PERMANENTE]}
    assert reg.despues is not None
    assert sorted(reg.despues["roles"]) == sorted([Rol.COMISION_PERMANENTE, Rol.JUNTA_GENERAL])


def test_retirar_rol_exige_motivo_y_no_borra_historial(ctx_tesorero: Contexto) -> None:
    u = crear("retira", Rol.COMISION_PERMANENTE, Rol.JUNTA_GENERAL)
    with pytest.raises(ValidationError):
        servicios.actualizar_roles(ctx_tesorero, u, [Rol.JUNTA_GENERAL], "")
    servicios.actualizar_roles(ctx_tesorero, u, [Rol.JUNTA_GENERAL], "rota de cargo")
    assert u.roles_vigentes() == [Rol.JUNTA_GENERAL]
    assert u.asignaciones.count() == 2  # la asignación anulada se conserva


def test_siempre_queda_un_tesorero(ctx_tesorero: Contexto, tesorero: object) -> None:
    with pytest.raises(ValidationError):
        servicios.actualizar_roles(ctx_tesorero, ctx_tesorero.usuario, [], "me voy")
    with pytest.raises(ValidationError):
        servicios.dar_de_baja(ctx_tesorero, ctx_tesorero.usuario, "me voy")


def test_baja_exige_motivo_y_desactiva(ctx_tesorero: Contexto) -> None:
    u = crear("baja", Rol.COMISION_PERMANENTE)
    with pytest.raises(ValidationError):
        servicios.dar_de_baja(ctx_tesorero, u, " ")
    servicios.dar_de_baja(ctx_tesorero, u, "deja el partido")
    u.refresh_from_db()
    assert not u.is_active and u.fecha_baja is not None
    assert not Client().login(username="baja", password=CLAVE)
    assert RegistroAuditoria.objects.filter(
        accion="usuario.baja", motivo="deja el partido"
    ).exists()


def test_pantallas_de_gestion_funcionan(cliente_tesorero: Client) -> None:
    assert cliente_tesorero.get("/usuarios/").status_code == 200
    r = cliente_tesorero.post(
        "/usuarios/nuevo/",
        {
            "username": "vocal",
            "first_name": "Vocal",
            "last_name": "Ficticio",
            "email": "",
            "password": CLAVE,
            "roles": [Rol.COMISION_PERMANENTE],
        },
    )
    assert r.status_code == 302
    pk = crear.__globals__["Usuario"].objects.get(username="vocal").pk
    assert cliente_tesorero.get(f"/usuarios/{pk}/roles/").status_code == 200
    assert cliente_tesorero.get(f"/usuarios/{pk}/baja/").status_code == 200


def test_contrasena_corta_se_rechaza(cliente_tesorero: Client) -> None:
    r = cliente_tesorero.post(
        "/usuarios/nuevo/",
        {
            "username": "debil",
            "first_name": "A",
            "last_name": "B",
            "password": "corta1",
            "roles": [Rol.COMISION_PERMANENTE],
        },
    )
    assert r.status_code == 200 and b"errorlist" in r.content


def test_accesos_quedan_registrados() -> None:
    crear("acc", Rol.COMISION_PERMANENTE)
    c = Client()
    assert not c.login(username="acc", password="mala")
    c.login(username="acc", password=CLAVE)
    c.post("/salir/")
    acciones = set(RegistroAuditoria.objects.values_list("accion", flat=True))
    assert {"acceso.fallido", "acceso.entrada", "acceso.salida"} <= acciones


def test_sesion_caduca_por_inactividad(settings: object) -> None:
    from django.conf import settings as s

    assert s.SESSION_COOKIE_AGE == s.SESION_MINUTOS * 60
    assert s.SESSION_SAVE_EVERY_REQUEST is True
