"""Pantallas de la memoria, del plan de tesorería y del panel de configuración de los anexos."""

import pytest
from django.test import Client

from apps.anexos.models import ParametrosAnexosCfg, SeccionMemoria, SeccionMemoriaCfg
from apps.auditoria.models import RegistroAuditoria
from tests.conftest import CLAVE
from tests.util_flujo import aprobar_cp, crear_escenario, proponer, version_valida

pytestmark = pytest.mark.django_db


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


def vocal(esc) -> Client:  # type: ignore[no-untyped-def]
    return cliente(esc.cp[0].username, "COMISION_PERMANENTE")


def junta(esc) -> Client:  # type: ignore[no-untyped-def]
    return cliente(esc.junta.username, "JUNTA_GENERAL")


def u(v, nombre: str) -> str:  # type: ignore[no-untyped-def]
    return f"/presupuestos/version/{v.pk}/{nombre}/"


# ------------------------------------------------------------------------ memoria


def test_la_memoria_completa_se_ve_con_sus_bloques_automaticos(esc) -> None:
    v = version_valida(esc)
    p = tesorero(esc).get(u(v, "memoria")).content.decode()
    assert "Memoria completa" in p and "Resumen ejecutivo" in p and "Generada por el sistema" in p
    assert "Hipótesis de cada línea" in p and "Parámetros legales usados" in p
    assert "Editar esta sección" in p


def test_la_memoria_incompleta_avisa_y_bloquea(esc) -> None:
    v = version_valida(esc)
    SeccionMemoria.objects.filter(version=v, clave="resumen").delete()
    p = tesorero(esc).get(u(v, "memoria")).content.decode()
    assert "Memoria incompleta" in p and "Falta escribir la sección" in p
    assert "Redactar esta sección" in p


def test_cada_rol_ve_la_memoria_solo_de_lo_que_le_corresponde(esc) -> None:
    v = version_valida(esc)
    assert vocal(esc).get(u(v, "memoria")).status_code == 404  # borrador: no es de la CP
    assert junta(esc).get(u(v, "memoria")).status_code == 404
    proponer(esc, v)
    cp = vocal(esc).get(u(v, "memoria"))
    assert cp.status_code == 200 and "Editar esta sección" not in cp.content.decode()
    assert junta(esc).get(u(v, "memoria")).status_code == 404  # aún no aprobada
    v2 = version_valida(esc, 2067)
    aprobar_cp(esc, v2)
    assert junta(esc).get(u(v2, "memoria")).status_code == 200


def test_la_memoria_sellada_no_ofrece_editar(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    p = tesorero(esc).get(u(v, "memoria")).content.decode()
    assert "Editar esta sección" not in p and "quedó sellada" in p
    assert tesorero(esc).get(u(v, "memoria/resumen")).status_code == 302


def test_redactar_arranca_con_la_plantilla_y_guarda(esc) -> None:
    v = version_valida(esc)
    SeccionMemoria.objects.filter(version=v, clave="contexto").delete()
    c = tesorero(esc)
    pagina = c.get(u(v, "memoria/contexto")).content.decode()
    assert "propuesto por la plantilla" in pagina and "[COMPLETAR" in pagina
    r = c.post(u(v, "memoria/contexto"), {"texto": "Actividad prevista. " * 20})
    assert r.status_code == 302
    assert SeccionMemoria.objects.get(version=v, clave="contexto").texto.startswith("Actividad")
    pagina = c.get(u(v, "memoria/contexto")).content.decode()
    assert "propuesto por la plantilla" not in pagina and "Actividad prevista." in pagina


def test_solo_el_tesorero_redacta_y_las_automaticas_no_se_redactan(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    assert vocal(esc).get(u(v, "memoria/resumen")).status_code == 403
    assert tesorero(esc).get(u(v, "memoria/cumplimiento")).status_code == 404
    assert tesorero(esc).get(u(v, "memoria/no-existe")).status_code == 404


# ---------------------------------------------------------------------- tesorería


def test_el_plan_de_tesoreria_se_ve_y_el_saldo_se_guarda(esc) -> None:
    v = version_valida(esc)
    c = tesorero(esc)
    p = c.get(u(v, "tesoreria")).content.decode()
    assert "Plan de tesorería mensual" in p and "Escenario base" in p and "Enero" in p
    assert "se cobra o se paga en el mes en que está presupuestado" in p
    r = c.post(u(v, "tesoreria"), {"saldo": "12.500,50"})
    assert r.status_code == 302
    v.refresh_from_db()
    assert str(v.saldo_inicial_tesoreria) == "12500.50"
    r = c.post(u(v, "tesoreria"), {"saldo": "12.50"})  # ambiguo: se rechaza
    assert "con coma decimal" in r.content.decode()


def test_la_tesoreria_no_se_edita_desde_otros_roles_ni_si_esta_sellada(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    p = vocal(esc).get(u(v, "tesoreria")).content.decode()
    assert "Guardar saldo inicial" not in p and "Escenario prudente" in p
    assert "Guardar saldo inicial" not in tesorero(esc).get(u(v, "tesoreria")).content.decode()


def test_un_escenario_sin_configurar_lo_dice(esc) -> None:
    v = version_valida(esc)
    ParametrosAnexosCfg.objects.filter(es_demo=True).update(
        reduccion_gastos_recurrente=None,
        reduccion_gastos_extraordinario=None,
        reduccion_gastos_condicionado=None,
    )
    p = tesorero(esc).get(u(v, "tesoreria")).content.decode()
    assert "Sin configurar" in p


# ------------------------------------------------------------------- el panel Anexos


def test_el_panel_solo_es_del_tesorero(esc) -> None:
    assert tesorero(esc).get("/anexos/").status_code == 200
    assert vocal(esc).get("/anexos/").status_code == 403
    assert junta(esc).get("/anexos/").status_code == 403
    assert vocal(esc).post("/anexos/secciones/nueva/", {"titulo": "x"}).status_code == 403
    assert Client().get("/anexos/").status_code == 302


def test_el_panel_edita_los_parametros_y_deja_auditoria(esc) -> None:
    c = tesorero(esc)
    pagina = c.get("/anexos/").content.decode()
    assert "Resumen ejecutivo" in pagina and "configuración de la DEMOSTRACIÓN" in pagina
    datos = {
        "variaciones_destacadas": "7",
        "marcas_pendiente": "[COMPLETAR\nXXX",
        "saldo_minimo_tesoreria": "1.500,00",
        "reduccion_ingresos_alta": "2,5",
        "reduccion_ingresos_media": "",
        "reduccion_ingresos_baja": "40",
        "reduccion_gastos_recurrente": "5",
        "reduccion_gastos_extraordinario": "",
        "reduccion_gastos_condicionado": "",
    }
    assert c.post("/anexos/", datos).status_code == 302
    p = ParametrosAnexosCfg.objects.get(es_demo=True)
    assert p.variaciones_destacadas == 7 and str(p.saldo_minimo_tesoreria) == "1500.00"
    assert str(p.reduccion_ingresos_alta) == "2.50" and p.reduccion_ingresos_media is None
    assert p.marcas == ["[COMPLETAR", "XXX"]
    r = RegistroAuditoria.objects.filter(accion="anexos.guardar_parametros").latest("id")
    antes, despues = dict(r.antes or {}), dict(r.despues or {})
    assert antes["saldo_minimo_tesoreria"] == "500.00" and despues["variaciones_destacadas"] == "7"


def test_el_panel_rechaza_porcentajes_absurdos(esc) -> None:
    c = tesorero(esc)
    datos = {
        "variaciones_destacadas": "5",
        "marcas_pendiente": "",
        "reduccion_ingresos_alta": "150",
    }
    r = c.post("/anexos/", datos)
    assert (
        r.status_code == 200
        and ParametrosAnexosCfg.objects.get(es_demo=True).variaciones_destacadas == 3
    )


def test_el_panel_edita_una_seccion_y_la_restablece(esc) -> None:
    c = tesorero(esc)
    c.get("/anexos/")
    s = SeccionMemoriaCfg.objects.get(clave="resumen", es_demo=True)
    pagina = c.get(f"/anexos/secciones/{s.pk}/").content.decode()
    assert "Texto de ayuda" in pagina and "{total_ingresos}" in pagina
    datos = {
        "titulo": "Resumen para la Junta",
        "orden": "1",
        "ambito": "TODOS",
        "obligatoria": "on",
        "activa": "on",
        "longitud_minima": "300",
        "ayuda": "Mi ayuda",
        "plantilla": "Mi plantilla {ejercicio}",
    }
    assert c.post(f"/anexos/secciones/{s.pk}/", datos).status_code == 302
    s.refresh_from_db()
    assert (s.titulo, s.longitud_minima, s.plantilla) == (
        "Resumen para la Junta",
        300,
        "Mi plantilla {ejercicio}",
    )
    assert c.post(f"/anexos/secciones/{s.pk}/restablecer/").status_code == 302
    s.refresh_from_db()
    assert (
        s.titulo == "Resumen ejecutivo" and s.longitud_minima == 150 and "[COMPLETAR" in s.plantilla
    )


def test_una_seccion_propia_se_crea_se_usa_y_no_se_restablece(esc) -> None:
    c = tesorero(esc)
    r = c.post("/anexos/secciones/nueva/", {"titulo": "Plan de actividades"})
    assert r.status_code == 302
    s = SeccionMemoriaCfg.objects.get(titulo="Plan de actividades", es_demo=True)
    assert s.clave.startswith("propia-") and not s.obligatoria
    v = version_valida(esc)
    assert "Plan de actividades" in c.get(u(v, "memoria")).content.decode()
    r = c.post(f"/anexos/secciones/{s.pk}/restablecer/", follow=True)
    assert "no hay valores propuestos" in r.content.decode()
    assert c.post("/anexos/secciones/nueva/", {"titulo": " "}).status_code == 302


def test_el_panel_real_y_el_de_demostracion_no_se_mezclan(catalogo) -> None:
    from tests.conftest import crear

    crear("tesorera_real", "TESORERO")
    c = cliente("tesorera_real", "TESORERO")
    pagina = c.get("/anexos/").content.decode()
    assert "configuración de la DEMOSTRACIÓN" not in pagina
    assert SeccionMemoriaCfg.objects.filter(es_demo=False).count() == 7
    assert ParametrosAnexosCfg.objects.get(es_demo=False).saldo_minimo_tesoreria is None
