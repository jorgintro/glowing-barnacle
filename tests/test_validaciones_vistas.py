from decimal import Decimal

import pytest
from django.test import Client

from apps.auditoria.servicios import Contexto
from apps.presupuesto import demo
from apps.presupuesto import donantes as dn
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import Donacion, Donante, Linea, VersionPresupuesto
from apps.usuarios.roles import Rol
from tests.conftest import CLAVE, crear
from tests.util_validaciones import donante, linea, nif

pytestmark = pytest.mark.django_db


def _cliente(usuario: str) -> Client:
    c = Client()
    assert c.login(username=usuario, password=CLAVE)
    return c


@pytest.fixture
def demo_cargada(catalogo, tesorero):
    demo.cargar_demo(Contexto(tesorero, Rol.TESORERO, "127.0.0.1"))


def _demo(anio: int) -> VersionPresupuesto:
    return VersionPresupuesto.objects.get(ejercicio__anio=anio, ejercicio__es_demo=True)


# --------------------------------------------------------------- panel de validaciones


def test_panel_de_validaciones_de_una_version_real_muestra_bloqueos(
    borrador, cliente_tesorero
) -> None:
    pagina = cliente_tesorero.get(
        f"/presupuestos/version/{borrador.pk}/validaciones/"
    ).content.decode()
    assert "bloqueo" in pagina and "L-007" in pagina and "Fuente:" in pagina
    resumen = cliente_tesorero.get(f"/presupuestos/version/{borrador.pk}/").content.decode()
    assert "Validaciones:" in resumen and "Ver el detalle" in resumen


def test_panel_de_una_version_demo_correcta_no_tiene_bloqueos(
    demo_cargada, cliente_tesorero
) -> None:
    v = _demo(2028)
    pagina = cliente_tesorero.get(f"/presupuestos/version/{v.pk}/validaciones/").content.decode()
    assert "Sin bloqueos" in pagina and "config/demo/" in pagina and "Superada" in pagina


def test_panel_del_caso_que_incumple_lista_las_incidencias(demo_cargada, cliente_tesorero) -> None:
    v = _demo(2031)
    pagina = cliente_tesorero.get(f"/presupuestos/version/{v.pk}/validaciones/").content.decode()
    for codigo in ("V-001", "V-006", "L-001", "L-004", "L-005"):
        assert codigo in pagina
    assert "no puede avanzar" in pagina


def test_el_panel_respeta_la_visibilidad_por_rol(demo_cargada) -> None:
    crear("vocal", Rol.COMISION_PERMANENTE)
    crear("junta", Rol.JUNTA_GENERAL)
    borrador, propuesto, aprobado = _demo(2028), _demo(2029), _demo(2030)
    for v, cp, junta in [(borrador, 404, 404), (propuesto, 200, 404), (aprobado, 200, 200)]:
        url = f"/presupuestos/version/{v.pk}/validaciones/"
        assert _cliente("vocal").get(url).status_code == cp
        assert _cliente("junta").get(url).status_code == junta


def test_la_cp_solo_ve_el_nif_enmascarado(demo_cargada) -> None:
    v = _demo(2031)
    VersionPresupuesto.objects.filter(pk=v.pk).update(estado=EstadoVersion.PROPUESTO)
    crear("vocal", Rol.COMISION_PERMANENTE)
    pagina = _cliente("vocal").get(f"/presupuestos/version/{v.pk}/validaciones/").content.decode()
    assert "Donante ficticio D1" in pagina
    assert "00000004G" not in pagina and "****004G" in pagina


# ---------------------------------------------------------------------- resultado


def test_el_tesorero_guarda_el_resultado(borrador, cliente_tesorero) -> None:
    url = f"/presupuestos/version/{borrador.pk}/resultado/"
    assert cliente_tesorero.get(url).status_code == 200
    r = cliente_tesorero.post(
        url,
        {
            "explicacion": "Déficit por la campaña",
            "plan_financiacion": "Préstamo",
            "endeudamiento": "1.500,00",
        },
    )
    assert r.status_code == 302
    borrador.refresh_from_db()
    assert borrador.plan_financiacion == "Préstamo" and borrador.endeudamiento_previsto == Decimal(
        "1500.00"
    )


def test_resultado_no_admite_importes_ambiguos_ni_negativos(borrador, cliente_tesorero) -> None:
    url = f"/presupuestos/version/{borrador.pk}/resultado/"
    for malo in ("12.50", "-100,00"):
        r = cliente_tesorero.post(
            url, {"explicacion": "x", "plan_financiacion": "", "endeudamiento": malo}
        )
        assert r.status_code == 200
    borrador.refresh_from_db()
    assert borrador.endeudamiento_previsto == Decimal("0.00")


def test_solo_el_tesorero_edita_el_resultado_y_solo_en_borrador(borrador, cliente_tesorero) -> None:
    crear("vocal", Rol.COMISION_PERMANENTE)
    url = f"/presupuestos/version/{borrador.pk}/resultado/"
    assert _cliente("vocal").get(url).status_code == 403
    borrador.estado = EstadoVersion.PROPUESTO
    borrador.save()
    assert cliente_tesorero.get(url).status_code == 302


# ----------------------------------------------------------------------- donantes


def test_gestion_de_donantes_desde_la_interfaz(catalogo, cliente_tesorero) -> None:
    datos = {"nombre": "Ana Ficticia", "nif": "12345678Z", "tipo_persona": "FISICA"}
    assert cliente_tesorero.post("/donantes/", datos).status_code == 302
    pagina = cliente_tesorero.get("/donantes/").content.decode()
    assert "Ana Ficticia" in pagina and "12345678Z" in pagina
    r = cliente_tesorero.post("/donantes/", datos)  # repetido
    assert r.status_code == 200 and "Ya existe" in r.content.decode()
    r = cliente_tesorero.post("/donantes/", {**datos, "nif": "12345678A", "nombre": "Otra"})
    assert r.status_code == 200 and "letra de control" in r.content.decode()
    d = Donante.objects.get()
    assert (
        cliente_tesorero.post(f"/donantes/{d.pk}/baja/", {"motivo": "Lo pide"}).status_code == 302
    )
    d.refresh_from_db()
    assert not d.activo


def test_solo_el_tesorero_ve_los_donantes(catalogo) -> None:
    crear("vocal", Rol.COMISION_PERMANENTE)
    crear("junta", Rol.JUNTA_GENERAL)
    for u in ("vocal", "junta"):
        assert _cliente(u).get("/donantes/").status_code == 403
        assert (
            _cliente(u).post("/donantes/", {"nombre": "x", "nif": "12345678Z"}).status_code == 403
        )
    assert Donante.objects.count() == 0


def test_donaciones_de_una_linea_desde_la_interfaz(
    borrador, ctx_tesorero, cliente_tesorero
) -> None:
    ln = linea(ctx_tesorero, borrador, "I.4.1", "1000", confianza="BAJA")
    d = donante(ctx_tesorero, 1, nombre="Beatriz Ficticia")
    url = f"/presupuestos/version/{borrador.pk}/lineas/{ln.pk}/donantes/"
    assert cliente_tesorero.get(url).status_code == 200
    r = cliente_tesorero.post(url, {"donante": d.pk, "importe": "400,00"})
    assert r.status_code == 302
    pagina = cliente_tesorero.get(url).content.decode()
    assert (
        "Beatriz Ficticia" in pagina and "400,00" in pagina and "600,00" in pagina
    )  # sin identificar
    don = Donacion.objects.get()
    r = cliente_tesorero.post(
        f"/presupuestos/version/{borrador.pk}/donaciones/{don.pk}/anular/", {"motivo": "Error"}
    )
    assert r.status_code == 302
    don.refresh_from_db()
    assert don.anulada


def test_las_lineas_de_cuotas_no_admiten_donantes_en_la_interfaz(
    borrador, ctx_tesorero, cliente_tesorero
) -> None:
    ln = linea(ctx_tesorero, borrador, "I.1.1", "100", confianza="ALTA")
    r = cliente_tesorero.get(f"/presupuestos/version/{borrador.pk}/lineas/{ln.pk}/donantes/")
    assert r.status_code == 302


def test_cp_y_junta_no_gestionan_donaciones(borrador, ctx_tesorero) -> None:
    ln = linea(ctx_tesorero, borrador, "I.4.1", "100", confianza="BAJA")
    d = donante(ctx_tesorero, 1)
    crear("vocal", Rol.COMISION_PERMANENTE)
    url = f"/presupuestos/version/{borrador.pk}/lineas/{ln.pk}/donantes/"
    assert _cliente("vocal").get(url).status_code == 403
    assert _cliente("vocal").post(url, {"donante": d.pk, "importe": "10,00"}).status_code == 403
    assert Donacion.objects.count() == 0


def test_el_formulario_de_linea_pide_origen_solo_en_ingresos(borrador, cliente_tesorero) -> None:
    ingreso = cliente_tesorero.get(
        f"/presupuestos/version/{borrador.pk}/lineas/nueva/I.5.1/"
    ).content.decode()
    gasto = cliente_tesorero.get(
        f"/presupuestos/version/{borrador.pk}/lineas/nueva/G.2.1/"
    ).content.decode()
    assert "Origen del ingreso" in ingreso and "Origen del ingreso" not in gasto


def test_el_origen_del_ingreso_se_guarda(borrador, cliente_tesorero) -> None:
    from apps.presupuesto.models import CuentaPGC

    datos = {
        "denominacion": "Merchandising",
        "cuenta": CuentaPGC.objects.get(codigo="70x").pk,
        "importe_anual": "100,00",
        "tipo": "RECURRENTE",
        "dimension": "ORDINARIO",
        "responsable": "Tesorería",
        "hipotesis_texto": "h",
        "hipotesis_fuente": "f",
        "confianza": "MEDIA",
        "origen_ingreso": "VENTA_PROPIA",
        "reparto": "UNIFORME",
    }
    r = cliente_tesorero.post(f"/presupuestos/version/{borrador.pk}/lineas/nueva/I.5.1/", datos)
    assert r.status_code == 302
    assert Linea.objects.get().origen_ingreso == "VENTA_PROPIA"


def test_el_nif_de_pruebas_es_valido() -> None:
    from apps.presupuesto.nif import validar_nif

    assert validar_nif(nif(1234), "FISICA") == nif(1234)
    assert dn.CAPITULOS_CON_DONANTES == ("I.2", "I.4")
