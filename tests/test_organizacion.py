import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.servicios import Contexto
from apps.organizacion import servicios as os_
from apps.organizacion.models import Cargo, Organizacion, Persona
from apps.usuarios.roles import Rol
from tests.conftest import CLAVE, crear
from tests.util_validaciones import nif

pytestmark = pytest.mark.django_db


# -------------------------------------------------------------------- organización


def test_los_valores_por_defecto_no_inventan_datos_de_personas(db) -> None:
    org = Organizacion.obtener()
    assert (org.nombre, org.localidad, org.denominacion_tesoreria) == (
        "Iniciativa Complutense",
        "Alcalá de Henares",
        "Tesorero",
    )
    assert Cargo.objects.count() == 0 and Persona.objects.count() == 0  # nada precargado


def test_guardar_datos_de_la_organizacion(tesorero, ctx_tesorero: Contexto) -> None:
    os_.guardar_organizacion(
        ctx_tesorero, nombre=" Mi Partido ", localidad="Madrid", denominacion_tesoreria="Gerente"
    )
    org = Organizacion.obtener()
    assert (org.nombre, org.localidad, org.denominacion_tesoreria) == (
        "Mi Partido",
        "Madrid",
        "Gerente",
    )
    assert Organizacion.objects.count() == 1  # registro único
    with pytest.raises(ValidationError):
        os_.guardar_organizacion(ctx_tesorero, nombre="", localidad="", denominacion_tesoreria=" ")


def test_la_denominacion_de_tesoreria_se_ve_en_la_interfaz(
    tesorero, ctx_tesorero, cliente_tesorero
) -> None:
    os_.guardar_organizacion(
        ctx_tesorero, nombre="X", localidad="Y", denominacion_tesoreria="Gerente"
    )
    assert "Gerente" in cliente_tesorero.get("/").content.decode()


# ------------------------------------------------------------------------ cargos


def test_la_lista_de_cargos_crea_reactiva_y_desactiva_sin_borrar(
    tesorero, ctx_tesorero: Contexto
) -> None:
    r = os_.sincronizar_cargos(ctx_tesorero, "Tesorero\n  Gerente \n\nSecretaria\nGERENTE\n")
    assert r == {"creados": 3, "reactivados": 0, "desactivados": 0}
    assert os_.texto_de_cargos().splitlines() == ["Tesorero", "Gerente", "Secretaria"]
    r = os_.sincronizar_cargos(ctx_tesorero, "Tesorero\nVocal")
    assert r == {"creados": 1, "reactivados": 0, "desactivados": 2}
    assert (
        Cargo.objects.count() == 4 and Cargo.objects.filter(activo=False).count() == 2
    )  # nada se borra
    r = os_.sincronizar_cargos(ctx_tesorero, "Tesorero\nGerente\nVocal")
    assert r["reactivados"] == 1 and r["desactivados"] == 0


def test_sincronizar_cargos_audita_solo_si_hay_cambios(tesorero, ctx_tesorero: Contexto) -> None:
    os_.sincronizar_cargos(ctx_tesorero, "Tesorero")
    n = RegistroAuditoria.objects.filter(accion="cargos.sincronizar").count()
    os_.sincronizar_cargos(ctx_tesorero, "Tesorero")
    assert RegistroAuditoria.objects.filter(accion="cargos.sincronizar").count() == n == 1


# ---------------------------------------------------------------------- personas


@pytest.fixture
def cargos(tesorero, ctx_tesorero):
    os_.sincronizar_cargos(ctx_tesorero, "Tesorero\nGerente\nSecretaria")
    return {c.denominacion: c for c in Cargo.objects.all()}


def test_crear_persona_con_varios_cargos(cargos, ctx_tesorero: Contexto) -> None:
    p = os_.crear_persona(
        ctx_tesorero,
        nombre=" Ana ",
        apellidos="Ficticia Prueba",
        dni=nif(123).lower(),
        cargos=[cargos["Tesorero"], cargos["Secretaria"]],
    )
    assert p.nombre_completo == "Ana Ficticia Prueba" and p.dni == nif(123)
    assert p.cargos_texto() == "Tesorero y Secretaria"
    assert p.activa and Persona.objects.count() == 1


def test_la_auditoria_de_personas_no_guarda_dni_ni_nombre(cargos, ctx_tesorero: Contexto) -> None:
    p = os_.crear_persona(
        ctx_tesorero, nombre="Berta", apellidos="Ficticia", dni=nif(7), cargos=[cargos["Gerente"]]
    )
    reg = RegistroAuditoria.objects.get(accion="persona.crear", entidad_id=str(p.pk))
    texto = str(reg.despues) + str(reg.antes) + reg.motivo
    assert "Berta" not in texto and nif(7) not in texto and "Ficticia" not in texto


@pytest.mark.parametrize(
    "malo",
    [{"nombre": " "}, {"apellidos": ""}, {"dni": "12345678A"}, {"dni": ""}, {"dni": "B12345674"}],
)
def test_datos_de_persona_incorrectos_se_rechazan(
    cargos, ctx_tesorero: Contexto, malo: dict
) -> None:
    datos = {"nombre": "Ana", "apellidos": "Ficticia", "dni": nif(5), "cargos": []}
    with pytest.raises(ValidationError):
        os_.crear_persona(ctx_tesorero, **{**datos, **malo})
    assert Persona.objects.count() == 0


def test_dni_repetido_y_cargo_inactivo(cargos, ctx_tesorero: Contexto) -> None:
    os_.crear_persona(ctx_tesorero, nombre="A", apellidos="B", dni=nif(9))
    with pytest.raises(ValidationError, match="Ya hay una persona"):
        os_.crear_persona(ctx_tesorero, nombre="C", apellidos="D", dni=nif(9))
    Cargo.objects.filter(pk=cargos["Gerente"].pk).update(activo=False)
    cargos["Gerente"].refresh_from_db()
    with pytest.raises(ValidationError, match="ya no está activo"):
        os_.crear_persona(
            ctx_tesorero, nombre="E", apellidos="F", dni=nif(10), cargos=[cargos["Gerente"]]
        )


def test_vincular_una_cuenta_de_usuario_solo_a_una_persona(cargos, ctx_tesorero: Contexto) -> None:
    u = crear("vocal", Rol.COMISION_PERMANENTE)
    p = os_.crear_persona(ctx_tesorero, nombre="A", apellidos="B", dni=nif(11), usuario=u)
    assert p.usuario == u and u.persona == p
    with pytest.raises(ValidationError, match="ya está asignada"):
        os_.crear_persona(ctx_tesorero, nombre="C", apellidos="D", dni=nif(12), usuario=u)


def test_actualizar_y_dar_de_baja(cargos, ctx_tesorero: Contexto) -> None:
    p = os_.crear_persona(
        ctx_tesorero, nombre="A", apellidos="B", dni=nif(13), cargos=[cargos["Tesorero"]]
    )
    os_.actualizar_persona(
        ctx_tesorero, p, nombre="Ana", apellidos="Bea", dni=nif(13), cargos=[cargos["Gerente"]]
    )
    p.refresh_from_db()
    assert p.nombre == "Ana" and p.cargos_texto() == "Gerente"
    with pytest.raises(ValidationError):
        os_.dar_de_baja_persona(ctx_tesorero, p, " ")
    os_.dar_de_baja_persona(ctx_tesorero, p, "Deja la organización")
    p.refresh_from_db()
    assert not p.activa and p.fecha_baja is not None and Persona.objects.filter(pk=p.pk).exists()
    with pytest.raises(ValidationError, match="de baja"):
        os_.actualizar_persona(ctx_tesorero, p, nombre="X", apellidos="Y", dni=nif(13))


def test_solo_el_tesorero_administra_la_organizacion(cargos) -> None:
    cp = crear("vocal", Rol.COMISION_PERMANENTE)
    ctx = Contexto(cp, Rol.COMISION_PERMANENTE)
    for llamada in (
        lambda: os_.guardar_organizacion(
            ctx, nombre="x", localidad="y", denominacion_tesoreria="z"
        ),
        lambda: os_.sincronizar_cargos(ctx, "Hackeo"),
        lambda: os_.crear_persona(ctx, nombre="a", apellidos="b", dni=nif(1)),
    ):
        with pytest.raises(PermissionDenied):
            llamada()


# ------------------------------------------------------------------------ vistas


def test_el_panel_funciona_de_principio_a_fin(tesorero, cliente_tesorero) -> None:
    assert cliente_tesorero.get("/organizacion/").status_code == 200
    r = cliente_tesorero.post(
        "/organizacion/datos/",
        {"nombre": "Mi Partido", "localidad": "Alcalá", "denominacion_tesoreria": "Gerente"},
    )
    assert r.status_code == 302 and Organizacion.obtener().denominacion_tesoreria == "Gerente"
    r = cliente_tesorero.post("/organizacion/cargos/", {"cargos": "Gerente\nSecretaria\nVocal"})
    assert r.status_code == 302 and Cargo.objects.filter(activo=True).count() == 3
    gerente = Cargo.objects.get(denominacion="Gerente")
    r = cliente_tesorero.post(
        "/organizacion/personas/nueva/",
        {"nombre": "Ana", "apellidos": "Ficticia", "dni": nif(21), "cargos": [gerente.pk]},
    )
    assert r.status_code == 302
    p = Persona.objects.get()
    pagina = cliente_tesorero.get("/organizacion/").content.decode()
    assert "Ana Ficticia" in pagina and nif(21) in pagina and "Gerente" in pagina
    assert cliente_tesorero.get(f"/organizacion/personas/{p.pk}/").status_code == 200
    r = cliente_tesorero.post(f"/organizacion/personas/{p.pk}/baja/", {"motivo": "Baja de prueba"})
    assert r.status_code == 302
    p.refresh_from_db()
    assert not p.activa


def test_el_formulario_de_persona_rechaza_un_dni_malo(tesorero, cliente_tesorero) -> None:
    r = cliente_tesorero.post(
        "/organizacion/personas/nueva/", {"nombre": "A", "apellidos": "B", "dni": "12345678A"}
    )
    assert r.status_code == 200 and "letra de control" in r.content.decode()
    assert Persona.objects.count() == 0


def test_cp_y_junta_no_ven_el_panel(tesorero) -> None:
    crear("vocal", Rol.COMISION_PERMANENTE)
    crear("junta", Rol.JUNTA_GENERAL)
    for u in ("vocal", "junta"):
        c = Client()
        assert c.login(username=u, password=CLAVE)
        assert c.get("/organizacion/").status_code == 403
        assert c.post("/organizacion/cargos/", {"cargos": "X"}).status_code == 403
        assert c.get("/organizacion/personas/nueva/").status_code == 403
    assert Cargo.objects.count() == 0
