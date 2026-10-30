from decimal import Decimal

import pytest
from django.test import Client

from apps.auditoria.servicios import Contexto
from apps.presupuesto import servicios as ps
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.forms import LineaForm
from apps.presupuesto.models import CuentaPGC, Linea, Partida
from apps.usuarios.roles import Rol
from tests.conftest import CLAVE, crear, poner_estado

pytestmark = pytest.mark.django_db


def _cliente(usuario: str) -> Client:
    c = Client()
    assert c.login(username=usuario, password=CLAVE)
    return c


def _datos_linea(**extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "denominacion": "Cuotas de prueba",
        "cuenta": CuentaPGC.objects.get(codigo="710").pk,
        "importe_anual": "1.234,56",
        "tipo": "RECURRENTE",
        "dimension": "ORDINARIO",
        "responsable": "Tesorería",
        "hipotesis_texto": "120 afiliados por 12 meses",
        "hipotesis_fuente": "Padrón ficticio",
        "confianza": "ALTA",
        "reparto": "UNIFORME",
    }
    base.update(extra)
    return base


def test_importes_en_formato_espanol(catalogo: None) -> None:
    p = Partida.objects.get(codigo="I.1.1")
    for texto, esperado in [("1234,56", "1234.56"), ("1.234,56", "1234.56"), ("0,5", "0.50")]:
        f = LineaForm(_datos_linea(importe_anual=texto), partida=p)
        assert f.is_valid(), f.errors
        assert f.cleaned_data["importe_anual"] == Decimal(esperado)
    assert not LineaForm(_datos_linea(importe_anual="abc"), partida=p).is_valid()


@pytest.mark.parametrize(
    "texto", ["12.50", "1234.56", "1,234.56", "1.23", "12,345", "--5", "1e5", "1,2,3"]
)
def test_importes_ambiguos_se_rechazan_en_vez_de_interpretarse(catalogo: None, texto: str) -> None:
    """«12.50» podría leerse como 1.250 en silencio: se rechaza con un mensaje claro."""
    p = Partida.objects.get(codigo="I.1.1")
    f = LineaForm(_datos_linea(importe_anual=texto), partida=p)
    assert not f.is_valid()
    assert "coma decimal" in str(f.errors["importe_anual"])


def test_importe_se_muestra_con_coma_al_editar(catalogo: None) -> None:
    p = Partida.objects.get(codigo="I.1.1")
    f = LineaForm(initial={"importe_anual": Decimal("1234.5")}, partida=p)
    assert 'value="1234,50"' in str(f["importe_anual"])


def test_ingreso_exige_confianza(catalogo: None) -> None:
    p = Partida.objects.get(codigo="I.1.1")
    f = LineaForm(_datos_linea(confianza=""), partida=p)
    assert not f.is_valid() and "confianza" in f.errors


def test_el_tesorero_elabora_un_borrador_desde_la_interfaz(
    catalogo: None, cliente_tesorero: Client
) -> None:
    r = cliente_tesorero.post(
        "/presupuestos/ejercicio/nuevo/",
        {"anio": 2044, "nombre": "Prueba", "hay_proceso_electoral": "on"},
    )
    assert r.status_code == 302
    version_url = r["Location"]
    assert cliente_tesorero.get(version_url).status_code == 200

    r = cliente_tesorero.post(f"{version_url}lineas/nueva/I.1.1/", _datos_linea())
    assert r.status_code == 302, getattr(r, "context", None) and r.context["form"].errors
    linea = Linea.objects.get()
    assert linea.importe_anual == Decimal("1234.56")
    pagina = cliente_tesorero.get(version_url).content.decode()
    assert "1.234,56" in pagina and "I.1.1.01" in pagina

    r = cliente_tesorero.post(
        f"{version_url}lineas/{linea.pk}/anular/", {"motivo": "Error de prueba"}
    )
    assert r.status_code == 302
    linea.refresh_from_db()
    assert linea.anulada


def test_errores_de_validacion_se_muestran_sin_guardar(
    catalogo: None, cliente_tesorero: Client, borrador
) -> None:
    url = f"/presupuestos/version/{borrador.pk}/lineas/nueva/I.1.1/"
    mal = _datos_linea(reparto="MANUAL", **{f"mes_{i}": "10,00" for i in range(1, 13)})
    r = cliente_tesorero.post(url, mal)
    assert r.status_code == 200 and "no coincide" in r.content.decode()
    assert Linea.objects.count() == 0
    r = cliente_tesorero.post(url, _datos_linea(reparto="MANUAL"))
    assert r.status_code == 200 and Linea.objects.count() == 0


def test_formulario_se_rellena_al_editar(
    borrador, ctx_tesorero: Contexto, cliente_tesorero: Client
) -> None:
    p = Partida.objects.get(codigo="I.1.1")
    linea = ps.guardar_linea(
        ctx_tesorero,
        borrador,
        partida=p,
        denominacion="Original",
        cuenta=CuentaPGC.objects.get(codigo="710"),
        importe_anual=Decimal("1200"),
        hipotesis=ps.DatosHipotesis("t", "f", "ALTA"),
        responsable="R",
    )
    r = cliente_tesorero.get(f"/presupuestos/version/{borrador.pk}/lineas/{linea.pk}/")
    assert r.status_code == 200 and "Original" in r.content.decode()


def test_version_no_borrador_es_de_solo_lectura_en_la_interfaz(
    borrador, cliente_tesorero: Client
) -> None:
    poner_estado(borrador, EstadoVersion.APROBADO_CP)
    pagina = cliente_tesorero.get(f"/presupuestos/version/{borrador.pk}/").content.decode()
    assert "solo lectura" in pagina and "Añadir línea" not in pagina
    r = cliente_tesorero.get(f"/presupuestos/version/{borrador.pk}/lineas/nueva/I.1.1/")
    assert r.status_code == 302
    r = cliente_tesorero.post(
        f"/presupuestos/version/{borrador.pk}/lineas/nueva/I.1.1/", _datos_linea()
    )
    assert r.status_code == 302 and Linea.objects.count() == 0


@pytest.mark.parametrize(
    ("estado", "cp_ve", "junta_ve"),
    [
        (EstadoVersion.BORRADOR, False, False),
        (EstadoVersion.PROPUESTO, True, False),
        (EstadoVersion.APROBADO_CP, True, True),
        (EstadoVersion.RATIFICADO_JG, True, True),
        (EstadoVersion.RECHAZADO, True, False),
        (EstadoVersion.MODIFICADO, True, True),
    ],
)
def test_visibilidad_por_rol(borrador, estado, cp_ve: bool, junta_ve: bool) -> None:
    poner_estado(borrador, estado)
    crear("vocal", Rol.COMISION_PERMANENTE)
    crear("junta", Rol.JUNTA_GENERAL)
    url = f"/presupuestos/version/{borrador.pk}/"
    assert (_cliente("vocal").get(url).status_code == 200) is cp_ve
    assert (_cliente("junta").get(url).status_code == 200) is junta_ve
    assert _cliente("tesorera").get(url).status_code == 200


def test_cp_y_junta_no_pueden_editar(borrador) -> None:
    crear("vocal", Rol.COMISION_PERMANENTE)
    crear("junta", Rol.JUNTA_GENERAL)
    for usuario in ("vocal", "junta"):
        c = _cliente(usuario)
        assert c.get("/presupuestos/ejercicio/nuevo/").status_code == 403
        assert c.get(f"/presupuestos/version/{borrador.pk}/lineas/nueva/").status_code == 403
        assert (
            c.post(
                f"/presupuestos/version/{borrador.pk}/lineas/nueva/I.1.1/", _datos_linea()
            ).status_code
            == 403
        )
    assert Linea.objects.count() == 0


def test_lista_y_configuracion(borrador, cliente_tesorero: Client) -> None:
    assert "Ejercicio de prueba" in cliente_tesorero.get("/presupuestos/").content.decode()
    conf = cliente_tesorero.get("/configuracion/").content.decode()
    assert "Pendiente de verificación" in conf and "pendiente de validación" in conf
    crear("vocal", Rol.COMISION_PERMANENTE)
    assert _cliente("vocal").get("/configuracion/").status_code == 200
    assert Client().get("/configuracion/").status_code == 302


def test_el_anio_no_lleva_separador_de_millares(borrador, cliente_tesorero: Client) -> None:
    """Con formato español, 2040 podría salir como «2 040»: el año no debe formatearse."""
    pagina = cliente_tesorero.get(f"/presupuestos/version/{borrador.pk}/").content.decode()
    assert "2040 · versión 1" in pagina
    assert "2 040" not in pagina and "2.040" not in pagina
    assert "<h2>2040" in cliente_tesorero.get("/presupuestos/").content.decode()


def test_linea_sin_hipotesis_muestra_aviso(
    borrador, ctx_tesorero: Contexto, cliente_tesorero: Client
) -> None:
    from apps.presupuesto.models import Hipotesis

    p = Partida.objects.get(codigo="I.1.1")
    linea = ps.guardar_linea(
        ctx_tesorero,
        borrador,
        partida=p,
        denominacion="X",
        cuenta=CuentaPGC.objects.get(codigo="710"),
        importe_anual=Decimal("10"),
        hipotesis=ps.DatosHipotesis("t", "f", "ALTA"),
        responsable="R",
    )
    Hipotesis.objects.filter(linea=linea).update(texto="", fuente="")
    pagina = cliente_tesorero.get(f"/presupuestos/version/{borrador.pk}/").content.decode()
    assert "Sin hipótesis" in pagina and "Hipótesis: ()" not in pagina
