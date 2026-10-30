"""Certificados de aprobación en HTML y PDF."""

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client

from apps.auditoria.models import RegistroAuditoria
from apps.organizacion import servicios as os_
from apps.presupuesto.models import Linea
from apps.salidas.certificados import (
    certificado_html,
    certificado_pdf,
    construir_certificado,
)
from tests.conftest import CLAVE
from tests.util_flujo import (
    A,
    aprobar_cp,
    crear_escenario,
    proponer,
    ratificar,
    version_valida,
    votar_y_cerrar,
)

pytestmark = pytest.mark.django_db
LETRAS = "TRWAGMYFPDXBNJZSQVHLCKE"


def dni(n: int) -> str:
    return f"{n:08d}{LETRAS[n % 23]}"


@pytest.fixture
def esc(catalogo):
    e = crear_escenario()
    os_.guardar_organizacion(
        e.tesorero(),
        nombre="Partido de Prueba",
        localidad="Villa Ficticia",
        denominacion_tesoreria="Gerente",
    )
    os_.sincronizar_cargos(e.tesorero(), "Gerente\nSecretaria\nPresidencia")
    return e


@pytest.fixture
def personas(esc):
    cargos = {c.denominacion: c for c in os_.Cargo.objects.all()}
    sec = os_.crear_persona(
        esc.tesorero(),
        nombre="Marta",
        apellidos="Ficticia Uno",
        dni=dni(501),
        cargos=[cargos["Secretaria"]],
        usuario=esc.cp[0],
        es_demo=True,
    )
    pres = os_.crear_persona(
        esc.tesorero(),
        nombre="Pedro",
        apellidos="Ficticio Dos",
        dni=dni(502),
        cargos=[cargos["Presidencia"], cargos["Gerente"]],
        es_demo=True,
    )
    return sec, pres


@pytest.fixture
def aprobada(esc):
    v = version_valida(esc)
    aprobar_cp(esc, v)
    return v


@pytest.fixture
def ratificada(esc):
    v = version_valida(esc, anio=2061)
    aprobar_cp(esc, v)
    ratificar(esc, v)
    return v


def cliente(esc, usuario, rol) -> Client:  # type: ignore[no-untyped-def]
    c = Client()
    assert c.login(username=usuario.username, password=CLAVE)
    c.post("/rol/", {"rol": rol})
    return c


# ------------------------------------------------------------------ construcción


def test_certificado_de_aprobacion_de_la_cp(aprobada, personas) -> None:
    sec, pres = personas
    d = construir_certificado(aprobada, "CP", sec, pres)
    texto = " ".join(d.parrafos)
    assert "Marta Ficticia Uno" in texto and dni(501) in texto and "Secretaria" in texto
    assert "APROBADO por la Comisión Permanente de Partido de Prueba" in texto
    assert (
        "Asistieron 4 de 4 miembros" in texto
        and "Votos a favor: 3" in texto
        and "abstenciones: 1" in texto
    )
    assert "propuesto por el cargo de Gerente" in texto  # cómo se llama la Tesorería aquí
    assert "Villa Ficticia" in texto
    assert ("Ingresos previstos", d.cifras[0][1]) == d.cifras[0] and "€" in d.cifras[0][1]
    assert len(d.asistentes) == 4 and d.votos is None
    assert d.huella == aprobada.hash and d.es_demo
    assert "Pendiente" not in texto and "ratificación por la Junta General" in texto


def test_el_nombre_de_la_organizacion_y_del_cargo_de_tesoreria_salen_en_el_certificado(
    esc, personas, aprobada
) -> None:
    d = construir_certificado(aprobada, "CP", personas[0])
    assert d.organizacion.nombre == "Partido de Prueba"
    texto = " ".join(d.parrafos)
    assert (
        "Partido de Prueba" in texto and "cargo de Gerente" in texto and "Villa Ficticia" in texto
    )


def test_el_voto_nominal_solo_sale_si_se_pide(aprobada, personas) -> None:
    d = construir_certificado(aprobada, "CP", personas[0], incluir_votos=True)
    assert d.votos is not None and len(d.votos) == 4
    assert {v for _, v in d.votos} == {"A favor", "Abstención"}
    assert any("Marta Ficticia Uno" in n for n, _ in d.votos)  # sale la ficha del panel


def test_certificado_de_ratificacion_de_la_junta(ratificada, personas) -> None:
    d = construir_certificado(ratificada, "JG", personas[1])
    texto = " ".join(d.parrafos)
    assert "RATIFICADO por la Junta General" in texto and "ACTA-PRUEBA" in texto
    assert "Pedro Ficticio Dos" in texto and "Gerente y Presidencia" in texto
    assert "convocada el" in texto


def test_no_se_certifica_lo_que_no_esta_aprobado(esc, personas) -> None:
    borrador = version_valida(esc)
    with pytest.raises(ValidationError, match="votación aprobada"):
        construir_certificado(borrador, "CP", personas[0])
    propuesta = version_valida(esc, anio=2061)
    proponer(esc, propuesta)
    with pytest.raises(ValidationError, match="votación aprobada"):
        construir_certificado(propuesta, "CP", personas[0])


def test_la_ratificacion_solo_se_certifica_si_la_junta_ratifico(aprobada, personas) -> None:
    with pytest.raises(ValidationError, match="no está ratificada"):
        construir_certificado(aprobada, "JG", personas[0])


def test_una_ratificacion_rechazada_no_se_certifica(esc, personas) -> None:
    v = version_valida(esc, anio=2062)
    aprobar_cp(esc, v)
    ratificar(esc, v, resultado="RECHAZADO")
    with pytest.raises(ValidationError, match="no está ratificada"):
        construir_certificado(v, "JG", personas[0])


def test_el_firmante_debe_estar_activo_y_tener_cargo(esc, personas, aprobada) -> None:
    sin_cargo = os_.crear_persona(
        esc.tesorero(), nombre="Sin", apellidos="Cargo", dni=dni(503), es_demo=True
    )
    with pytest.raises(ValidationError, match="ningún cargo|no tiene ningún cargo"):
        construir_certificado(aprobada, "CP", sin_cargo)
    os_.dar_de_baja_persona(esc.tesorero(), personas[1], "Baja de prueba")
    personas[1].refresh_from_db()
    with pytest.raises(ValidationError, match="de baja"):
        construir_certificado(aprobada, "CP", personas[0], personas[1])
    with pytest.raises(ValidationError, match="desconocido"):
        construir_certificado(aprobada, "XX", personas[0])


def test_no_se_emite_certificado_de_una_version_manipulada(aprobada, personas) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE presupuesto_linea DISABLE TRIGGER flujo_contenido_linea")
    Linea.objects.filter(version=aprobada).update(importe_anual=1)
    with pytest.raises(ValidationError, match="integridad"):
        construir_certificado(aprobada, "CP", personas[0])


def test_una_modificacion_aprobada_solo_por_la_cp_se_certifica_como_definitiva(
    esc, personas
) -> None:
    from apps.flujo import servicios as fs
    from tests.util_flujo import vigente
    from tests.util_validaciones import linea

    base = vigente(esc, anio=2063)
    m = fs.crear_modificacion(esc.tesorero(), base, "Obra menor")
    linea(esc.tesorero(), m, "G.2.5", "400", tipo="EXTRAORDINARIO")
    votacion = proponer(esc, m)
    votar_y_cerrar(esc, votacion, {0: A, 1: A, 2: A})
    m.refresh_from_db()
    assert m.estado == "MODIFICADO"
    texto = " ".join(construir_certificado(m, "CP", personas[0]).parrafos)
    assert "modificación presupuestaria" in texto and "es definitiva con esta aprobación" in texto


# ------------------------------------------------------------------- HTML y PDF


def test_el_html_es_autonomo_y_lleva_huella_firmantes_y_marca_de_demo(aprobada, personas) -> None:
    d = construir_certificado(aprobada, "CP", personas[0], personas[1])
    html = certificado_html(d)
    assert html.startswith("<!doctype html>") and "<style>" in html
    assert (
        "http://" not in html and "https://" not in html and "<script src" not in html
    )  # sin recursos externos
    assert aprobada.hash in html and "Marta Ficticia Uno" in html and "Pedro Ficticio Dos" in html
    assert dni(501) in html and dni(502) in html and "Vº Bº" in html
    assert "DATOS FICTICIOS DE DEMOSTRACIÓN · SIN VALIDEZ" in html
    assert "No es una firma electrónica" in html and "@media print" in html
    assert "2060" in html and "2.060" not in html  # el año, sin separador de millares


def test_el_certificado_real_no_lleva_marca_de_demo(esc, personas, aprobada) -> None:
    d = construir_certificado(aprobada, "CP", personas[0])
    d.es_demo = False
    assert "SIN VALIDEZ" not in certificado_html(d)


def test_el_pdf_es_valido_y_contiene_lo_esencial(aprobada, personas) -> None:
    d = construir_certificado(aprobada, "CP", personas[0], personas[1], incluir_votos=True)
    pdf = certificado_pdf(d)
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF") and len(pdf) > 2000
    for fragmento in (
        b"CERTIFICA",
        aprobada.hash[:32].encode(),
        aprobada.hash[32:].encode(),
        b"APROBADO",
    ):
        assert fragmento in pdf, fragmento
    assert b"SIN VALIDEZ" in pdf  # marca de agua de demostración
    assert certificado_pdf(d) == pdf  # determinista


def test_el_pdf_de_la_junta(ratificada, personas) -> None:
    pdf = certificado_pdf(construir_certificado(ratificada, "JG", personas[1]))
    assert pdf.startswith(b"%PDF-") and b"RATIFICADO" in pdf and b"ACTA-PRUEBA" in pdf


# ------------------------------------------------------------------------ vistas


def test_la_pantalla_de_certificados_orienta_segun_el_estado(
    esc, personas, aprobada, ratificada
) -> None:
    c = cliente(esc, esc.t, "TESORERO")
    pagina = c.get(f"/presupuestos/version/{aprobada.pk}/certificados/").content.decode()
    assert (
        "Aprobación por la Comisión Permanente" in pagina
        and "Ratificación por la Junta" not in pagina
    )
    pagina = c.get(f"/presupuestos/version/{ratificada.pk}/certificados/").content.decode()
    assert "Ratificación por la Junta General" in pagina and "Descargar en PDF" in pagina


def test_sin_personas_con_cargo_se_remite_al_panel(catalogo) -> None:
    e = crear_escenario()
    v = version_valida(e)
    aprobar_cp(e, v)
    pagina = (
        cliente(e, e.t, "TESORERO")
        .get(f"/presupuestos/version/{v.pk}/certificados/")
        .content.decode()
    )
    assert "panel de la organización" in pagina and "Descargar en PDF" not in pagina


def test_sin_aprobacion_no_hay_nada_que_certificar(esc, personas) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    c = cliente(esc, esc.t, "TESORERO")
    assert (
        "todavía no tiene nada que certificar"
        in c.get(f"/presupuestos/version/{v.pk}/certificados/").content.decode()
    )


def test_generar_el_certificado_html_y_pdf_desde_la_interfaz_y_queda_auditado(
    esc, personas, aprobada
) -> None:
    sec, pres = personas
    c = cliente(esc, esc.t, "TESORERO")
    base = f"/presupuestos/version/{aprobada.pk}/certificado/"
    consulta = {"tipo": "CP", "firmante": sec.pk, "visto_bueno": pres.pk}
    r = c.get(base, {**consulta, "formato": "html"})
    assert (
        r.status_code == 200
        and "text/html" in r["Content-Type"]
        and "CERTIFICA" in r.content.decode()
    )
    r = c.get(base, {**consulta, "formato": "pdf"})
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert r["Content-Disposition"] == 'attachment; filename="certificado_cp_2060_v1.pdf"'
    assert r.content.startswith(b"%PDF-")
    registros = RegistroAuditoria.objects.filter(accion="certificado.generar").order_by("id")
    assert [(x.despues or {})["formato"] for x in registros] == ["html", "pdf"]
    assert registros[0].despues is not None and registros[1].despues is not None
    assert registros[0].despues["huella"] == aprobada.hash
    assert "Marta" not in str(registros[0].despues) and dni(501) not in str(registros[0].despues)


def test_los_certificados_los_pueden_pedir_cp_y_junta_cuando_la_version_les_es_visible(
    esc, personas, aprobada
) -> None:
    sec, _ = personas
    consulta = {"tipo": "CP", "firmante": sec.pk, "formato": "html"}
    base = f"/presupuestos/version/{aprobada.pk}/certificado/"
    assert cliente(esc, esc.cp[0], "COMISION_PERMANENTE").get(base, consulta).status_code == 200
    assert cliente(esc, esc.junta, "JUNTA_GENERAL").get(base, consulta).status_code == 200


def test_peticiones_incorrectas_vuelven_a_la_pantalla_con_un_aviso(esc, personas, aprobada) -> None:
    c = cliente(esc, esc.t, "TESORERO")
    base = f"/presupuestos/version/{aprobada.pk}/certificado/"
    assert c.get(base, {"tipo": "CP", "formato": "html"}).status_code == 302  # falta firmante
    assert (
        c.get(base, {"tipo": "JG", "firmante": personas[0].pk, "formato": "html"}).status_code
        == 302
    )
    assert (
        c.get(base, {"tipo": "CP", "firmante": personas[0].pk, "formato": "docx"}).status_code
        == 302
    )
    assert not RegistroAuditoria.objects.filter(accion="certificado.generar").exists()


def test_sin_sesion_no_hay_certificados(aprobada) -> None:
    assert Client().get(f"/presupuestos/version/{aprobada.pk}/certificados/").status_code == 302
