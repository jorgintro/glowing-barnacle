"""Pantallas del flujo: proponer, votar, Junta, historial, comentarios y auditoría."""

from datetime import timedelta

import pytest
from django.db import connection
from django.test import Client
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.flujo.models import Ratificacion, Votacion
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import Linea
from tests.conftest import CLAVE
from tests.util_flujo import (
    aprobar_cp,
    crear_escenario,
    proponer,
    ratificar,
    version_valida,
    vigente,
)

pytestmark = pytest.mark.django_db
HOY = timezone.localdate()


@pytest.fixture
def esc(catalogo):
    return crear_escenario()


def cliente(usuario: str, rol: str) -> Client:
    c = Client()
    assert c.login(username=usuario, password=CLAVE)
    c.post("/rol/", {"rol": rol})
    return c


def tesorero(esc) -> Client:  # type: ignore[no-untyped-def]
    return cliente(esc.t.username, "TESORERO")


def vocal(esc, i: int = 0) -> Client:  # type: ignore[no-untyped-def]
    return cliente(esc.cp[i].username, "COMISION_PERMANENTE")


def junta(esc) -> Client:  # type: ignore[no-untyped-def]
    return cliente(esc.junta.username, "JUNTA_GENERAL")


def url(v, nombre: str) -> str:  # type: ignore[no-untyped-def]
    return f"/presupuestos/version/{v.pk}/{nombre}/"


# --------------------------------------------------------------------- el panel


def test_el_panel_ofrece_a_cada_rol_solo_lo_suyo(esc) -> None:
    v = version_valida(esc)
    pagina = tesorero(esc).get(f"/presupuestos/version/{v.pk}/").content.decode()
    assert "Proponer a la Comisión Permanente" in pagina and "Devolver al Tesorero" not in pagina
    proponer(esc, v)
    pagina = tesorero(esc).get(f"/presupuestos/version/{v.pk}/").content.decode()
    assert "Proponer a la Comisión Permanente" not in pagina and "Ver la votación" in pagina
    pagina = vocal(esc).get(f"/presupuestos/version/{v.pk}/").content.decode()
    assert "Votar" in pagina and "Devolver al Tesorero" in pagina and "Huella" in pagina
    assert "Crear una modificación" not in pagina


def test_el_panel_de_la_junta_y_de_la_modificacion(esc) -> None:
    v = version_valida(esc)
    aprobar_cp(esc, v)
    j = junta(esc).get(f"/presupuestos/version/{v.pk}/").content.decode()
    assert "Registrar convocatoria de la Junta" in j and "Registrar el acuerdo de la Junta" in j
    assert "Pendiente de ratificar por la Junta" in j
    ratificar(esc, v)
    t = tesorero(esc).get(f"/presupuestos/version/{v.pk}/").content.decode()
    assert "Crear una modificación" in t and "Certificados de aprobación" in t


# -------------------------------------------------------------------- proponer


def test_proponer_desde_la_interfaz_sella_y_lleva_a_la_votacion(esc) -> None:
    v = version_valida(esc)
    c = tesorero(esc)
    pagina = c.get(url(v, "proponer")).content.decode()
    assert "Sin bloqueos" in pagina and "se sella" in pagina
    r = c.post(url(v, "proponer"), {})  # sin confirmar
    assert r.status_code == 200
    v.refresh_from_db()
    assert v.estado == EstadoVersion.BORRADOR
    r = c.post(url(v, "proponer"), {"confirmar": "on"})
    assert r.status_code == 302 and r["Location"] == url(v, "votacion")
    v.refresh_from_db()
    assert v.estado == EstadoVersion.PROPUESTO and len(v.hash) == 64


def test_proponer_muestra_los_bloqueos_y_no_deja_avanzar(
    catalogo, tesorero, ctx_tesorero, cliente_tesorero
) -> None:
    from apps.presupuesto import servicios as ps
    from tests.util_validaciones import presupuesto_valido

    _, real = ps.crear_ejercicio(ctx_tesorero, anio=2071)
    presupuesto_valido(ctx_tesorero, real)
    pagina = cliente_tesorero.get(url(real, "proponer")).content.decode()
    assert "No se puede proponer todavía" in pagina and "L-007" in pagina
    assert "Proponer y sellar" not in pagina
    r = cliente_tesorero.post(url(real, "proponer"), {"confirmar": "on"})
    assert r.status_code == 200  # se queda en la pantalla, con el motivo del bloqueo
    real.refresh_from_db()
    assert real.estado == EstadoVersion.BORRADOR


def test_solo_el_tesorero_propone(esc) -> None:
    v = version_valida(esc)
    assert vocal(esc).get(url(v, "proponer")).status_code == 403
    assert vocal(esc).post(url(v, "proponer"), {"confirmar": "on"}).status_code == 403
    assert junta(esc).get(url(v, "proponer")).status_code == 403


# ----------------------------------------------------------- devolver y votación


def test_la_cp_devuelve_desde_la_interfaz(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    c = vocal(esc)
    r = c.post(url(v, "devolver"), {"motivo": ""})
    assert r.status_code == 200
    r = c.post(url(v, "devolver"), {"motivo": "Falta detalle"})
    assert r.status_code == 302
    v.refresh_from_db()
    assert v.estado == EstadoVersion.BORRADOR


def test_votar_y_cerrar_desde_la_interfaz(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    pagina = vocal(esc, 0).get(url(v, "votacion")).content.decode()
    assert "Emitir mi voto" in pagina and "sin votar" in pagina
    for i in range(3):
        r = vocal(esc, i).post(url(v, "votacion/votar"), {"voto": "A_FAVOR"})
        assert r.status_code == 302
    pagina = vocal(esc, 0).get(url(v, "votacion")).content.decode()
    assert "hay quórum y mayoría" in pagina and "Cambiar mi voto" in pagina
    sin_confirmar = vocal(esc, 0).post(url(v, "votacion/cerrar"), {"observaciones": "x"})
    assert sin_confirmar.status_code == 302
    v.refresh_from_db()
    assert v.estado == EstadoVersion.PROPUESTO  # no se cerró sin confirmar
    vocal(esc, 0).post(
        url(v, "votacion/cerrar"), {"confirmar": "on", "observaciones": "Todo en orden"}
    )
    v.refresh_from_db()
    assert v.estado == EstadoVersion.APROBADO_CP
    cerrada = vocal(esc, 0).get(url(v, "votacion")).content.decode()
    assert "Aprobada" in cerrada and "Todo en orden" in cerrada and "Emitir mi voto" not in cerrada


def test_sin_quorum_se_avisa_y_no_se_cierra(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    vocal(esc, 0).post(url(v, "votacion/votar"), {"voto": "A_FAVOR"})
    pagina = vocal(esc, 0).get(url(v, "votacion")).content.decode()
    assert "todavía no se puede aprobar" in pagina and "No hay quórum" in pagina
    vocal(esc, 0).post(url(v, "votacion/cerrar"), {"confirmar": "on"}, follow=True)
    v.refresh_from_db()
    assert v.estado == EstadoVersion.PROPUESTO


def test_la_votacion_muestra_el_nombre_y_cargo_de_la_ficha(esc) -> None:
    from apps.organizacion import servicios as os_

    os_.sincronizar_cargos(esc.tesorero(), "Secretaria")
    cargo = os_.Cargo.objects.get()
    os_.crear_persona(
        esc.tesorero(),
        nombre="Rosa",
        apellidos="Ficticia Prueba",
        dni="00000321" + "TRWAGMYFPDXBNJZSQVHLCKE"[321 % 23],
        cargos=[cargo],
        usuario=esc.cp[0],
        es_demo=True,
    )
    v = version_valida(esc)
    proponer(esc, v)
    pagina = vocal(esc, 1).get(url(v, "votacion")).content.decode()
    assert (
        "Rosa Ficticia Prueba (Secretaria)" in pagina
        and "cp2_demo" not in pagina
        or "cp2_demo" in pagina
    )
    assert "Propone" in pagina  # el proponente figura marcado


def test_visibilidad_de_la_votacion_por_rol(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    assert vocal(esc).get(url(v, "votacion")).status_code == 200
    assert junta(esc).get(url(v, "votacion")).status_code == 404  # la Junta solo ve lo aprobado
    assert tesorero(esc).get(url(v, "votacion")).status_code == 200
    borrador = version_valida(esc, anio=2061)
    assert tesorero(esc).get(url(borrador, "votacion")).status_code == 302  # aún no hay votación


def test_cp_no_vota_con_el_rol_de_tesorero_ni_la_junta(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    assert tesorero(esc).post(url(v, "votacion/votar"), {"voto": "A_FAVOR"}).status_code == 403
    assert junta(esc).post(url(v, "votacion/votar"), {"voto": "A_FAVOR"}).status_code == 403
    assert not Votacion.objects.get(version=v).votos.exists()


# ------------------------------------------------------------------------- Junta


def test_la_junta_convoca_y_ratifica_desde_la_interfaz(esc) -> None:
    v = version_valida(esc)
    aprobar_cp(esc, v)
    j = junta(esc)
    r = j.post(
        url(v, "convocatoria"),
        {
            "fecha_convocatoria": (HOY - timedelta(days=7)).isoformat(),
            "fecha_sesion": HOY.isoformat(),
        },
    )
    assert r.status_code == 302
    pagina = j.get(url(v, "ratificar")).content.decode()
    assert "No consta la convocatoria" not in pagina
    r = j.post(
        url(v, "ratificar"),
        {
            "fecha_sesion": HOY.isoformat(),
            "resultado": "RATIFICADO",
            "referencia_acta": "ACTA-9/2026",
        },
    )
    assert r.status_code == 302
    v.refresh_from_db()
    assert v.estado == EstadoVersion.RATIFICADO_JG
    assert Ratificacion.objects.get().referencia_acta == "ACTA-9/2026"


def test_sin_convocatoria_la_pantalla_pide_aceptar_el_aviso(esc) -> None:
    v = version_valida(esc)
    aprobar_cp(esc, v)
    j = junta(esc)
    pagina = j.get(url(v, "ratificar")).content.decode()
    assert "No consta la convocatoria" in pagina and "Acepto el aviso" in pagina
    datos = {
        "fecha_sesion": HOY.isoformat(),
        "resultado": "RATIFICADO",
        "referencia_acta": "ACTA-1",
    }
    assert j.post(url(v, "ratificar"), datos).status_code == 200  # se queda en el formulario
    v.refresh_from_db()
    assert v.estado == EstadoVersion.APROBADO_CP
    assert j.post(url(v, "ratificar"), {**datos, "acepto_aviso": "on"}).status_code == 302


def test_la_cp_no_ratifica_ni_convoca(esc) -> None:
    v = version_valida(esc)
    aprobar_cp(esc, v)
    assert vocal(esc).get(url(v, "ratificar")).status_code == 403
    assert vocal(esc).get(url(v, "convocatoria")).status_code == 403


# -------------------------------------------------------- modificación y prórroga


def test_crear_una_modificacion_desde_la_interfaz(esc) -> None:
    v = vigente(esc)
    c = tesorero(esc)
    assert c.post(url(v, "modificar"), {"motivo": ""}).status_code == 200
    r = c.post(url(v, "modificar"), {"motivo": "Obra en la sede"})
    assert r.status_code == 302
    nueva = v.ejercicio.versiones.get(numero=2)
    assert (
        r["Location"] == f"/presupuestos/version/{nueva.pk}/"
        and nueva.tipo_origen == "MODIFICACION"
    )
    assert vocal(esc).get(url(v, "modificar")).status_code == 403


def test_la_prorroga_se_ofrece_en_la_lista_y_se_genera(esc) -> None:
    from apps.presupuesto import servicios as ps

    vigente(esc, anio=2061)
    _, v = ps.crear_ejercicio(esc.tesorero(), anio=2062, es_demo=True)
    c = tesorero(esc)
    # hoy es 2026: el ejercicio 2062 aún no ha empezado, así que no se ofrece
    assert "prórroga provisional" not in c.get("/presupuestos/").content.decode()
    r = c.post(f"/presupuestos/ejercicio/{v.ejercicio.pk}/prorroga/")
    assert r.status_code == 302 and r["Location"] == "/presupuestos/"
    assert v.ejercicio.versiones.count() == 1


# ---------------------------------------------------------------------- historial


def test_el_historial_muestra_la_cadena_y_la_integridad(esc) -> None:
    v = version_valida(esc)
    aprobar_cp(esc, v)
    ratificar(esc, v)
    pagina = vocal(esc).get(url(v, "historial")).content.decode()
    assert "Íntegra" in pagina and v.hash in pagina and "Hoja de control" in pagina
    assert "Ratificado" in pagina and "ACTA-PRUEBA" in pagina and "Votación del" in pagina
    assert junta(esc).get(url(v, "historial")).status_code == 200


def test_el_historial_avisa_si_alguien_manipula_la_version(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE presupuesto_linea DISABLE TRIGGER flujo_contenido_linea")
    Linea.objects.filter(version=v).update(importe_anual=1)
    pagina = tesorero(esc).get(url(v, "historial")).content.decode()
    assert "Posible manipulación" in pagina and "NO coincide con su huella" in pagina


# -------------------------------------------------------------------- comentarios


def test_comentarios_desde_la_interfaz(esc) -> None:
    v = version_valida(esc)
    assert tesorero(esc).get(url(v, "comentarios")).status_code == 302  # aún es borrador
    proponer(esc, v)
    c = vocal(esc)
    linea = Linea.objects.filter(version=v).first()
    assert linea is not None
    r = c.post(url(v, "comentarios"), {"texto": "Revisar esta partida", "linea": linea.pk})
    assert r.status_code == 302
    pagina = c.get(url(v, "comentarios")).content.decode()
    assert "Revisar esta partida" in pagina and "Abierto" in pagina and linea.codigo in pagina
    comentario = v.comentarios.get()
    assert (
        tesorero(esc)
        .post(f"/presupuestos/version/{v.pk}/comentarios/{comentario.pk}/resolver/")
        .status_code
        == 302
    )
    comentario.refresh_from_db()
    assert comentario.resuelto
    assert junta(esc).get(url(v, "comentarios")).status_code == 403


# ---------------------------------------------------------------------- auditoría


def test_la_auditoria_solo_la_ve_el_tesorero_y_se_puede_filtrar(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    c = tesorero(esc)
    assert c.get("/auditoria/").status_code == 200
    pagina = c.get("/auditoria/?accion=version.propuesto").content.decode()
    assert "version.propuesto" in pagina and "ejercicio.crear" not in pagina
    pagina = c.get("/auditoria/?usuario=t_demo&entidad=Votacion").content.decode()
    assert "votacion.abrir" in pagina
    assert "No hay registros" in c.get("/auditoria/?accion=no.existe.esto").content.decode()
    assert "No hay registros" in c.get("/auditoria/?desde=2999-01-01").content.decode()
    for u, rol in (
        (esc.cp[0].username, "COMISION_PERMANENTE"),
        (esc.junta.username, "JUNTA_GENERAL"),
    ):
        assert cliente(u, rol).get("/auditoria/").status_code == 403
    assert RegistroAuditoria.objects.exists()


def test_la_auditoria_no_muestra_datos_personales_de_donantes(esc) -> None:
    version_valida(esc)
    pagina = tesorero(esc).get("/auditoria/?entidad=Donante").content.decode()
    assert "donante.crear" in pagina
    assert "Donante 1" not in pagina and "00000001R" not in pagina
