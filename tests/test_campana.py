"""Presupuesto de campaña: límite, envío directo, reglas L-004 y L-012 a L-015, V-011."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction

from apps.anexos import servicios as an
from apps.anexos.campana import construir_plan_campana
from apps.anexos.memoria import construir_memoria
from apps.anexos.models import ParametrosAnexosCfg, ProcesoElectoral
from apps.auditoria.models import RegistroAuditoria
from apps.flujo import servicios as fs
from apps.flujo.sello import calcular_hash, contenido_canonico
from apps.presupuesto import donantes as dn
from apps.presupuesto.configuracion import cargar_configuracion
from apps.presupuesto.errores import VersionNoEditable
from apps.presupuesto.models import Linea
from apps.validaciones.motor import validar_version
from tests.util_flujo import aprobar_cp, crear_escenario, proponer, ratificar, version_valida
from tests.util_validaciones import (
    HOY,
    cfg_demo,
    con_param,
    donante,
    linea,
    proceso_electoral,
    sin_verificar,
    validar,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def esc(catalogo):
    return crear_escenario()


@pytest.fixture
def camp(esc):
    v = version_valida(esc, 2070, campana=True)
    return esc, v


def D(x: str) -> Decimal:
    return Decimal(x)


def msgs(res, codigo: str) -> list[str]:
    return [i.mensaje for i in res.incidencias if i.codigo == codigo]


# ----------------------------------------------------------------- límite y plan


def test_el_limite_sale_de_los_habitantes_y_la_tarifa(camp) -> None:
    _, v = camp
    plan = construir_plan_campana(v, cfg_demo())
    assert plan.limite == D("14960.00")  # 136.000 × 0,11
    assert plan.gasto_total == D("5000.00") and plan.gasto_computable == D("5000.00")
    assert str(plan.porcentaje_del_limite) == "33.4" and not plan.supera_el_limite
    assert plan.subvenciones == D("4000.00") and plan.a_cubrir_con_fondos_ordinarios == D("1000.00")


def test_las_provincias_con_gasto_adicional_amplian_el_limite(camp) -> None:
    esc, v = camp
    proceso_electoral(esc.tesorero(), v, provincias_adicional=2)
    assert construir_plan_campana(v, cfg_demo()).limite == D("114960.00")  # + 2 × 50.000 (demo)


def test_sin_habitantes_o_sin_verificar_no_hay_limite_y_l004_bloquea(camp) -> None:
    esc, v = camp
    proceso_electoral(esc.tesorero(), v, habitantes_derecho=None)
    assert construir_plan_campana(v, cfg_demo()).limite is None
    assert any("habitantes" in m for m in msgs(validar(v), "L-004"))
    proceso_electoral(esc.tesorero(), v)
    res = validar(v, sin_verificar(cfg_demo(), "gasto_electoral_euros_por_habitante"))
    assert any("gasto_electoral_euros_por_habitante" in m for m in msgs(res, "L-004"))


def test_la_provincia_adicional_sin_verificar_bloquea_solo_si_se_usa(camp) -> None:
    esc, v = camp
    cfg = sin_verificar(cfg_demo(), "gasto_electoral_adicional_por_provincia")
    assert "L-004" not in {i.codigo for i in validar(v, cfg).incidencias}
    proceso_electoral(esc.tesorero(), v, provincias_adicional=1)
    assert any("adicional_por_provincia" in m for m in msgs(validar(v, cfg), "L-004"))


# ------------------------------------------------------------------ envío directo


def _con_envio(esc, v, gasto: str = "3000", **proceso) -> None:
    linea(esc.tesorero(), v, "G.7.13", gasto, tipo="EXTRAORDINARIO")
    datos = {"subvencion_envio_aplicable": True, "electores_envio": 20000}
    datos.update(proceso)
    proceso_electoral(esc.tesorero(), v, **datos)


def test_el_envio_subvencionado_queda_fuera_del_limite(camp) -> None:
    esc, v = camp
    _con_envio(esc, v)  # subvención estimada: 20.000 × 0,20 = 4.000 > 3.000 de gasto
    plan = construir_plan_campana(v, cfg_demo())
    assert plan.gasto_envio == D("3000.00") and plan.exclusion_envio == D("3000.00")
    assert plan.gasto_total == D("8000.00") and plan.gasto_computable == D("5000.00")


def test_solo_se_descuenta_hasta_la_subvencion_de_envio(camp) -> None:
    esc, v = camp
    _con_envio(esc, v, gasto="9000", electores_envio=10000)  # subvención: 2.000
    plan = construir_plan_campana(v, cfg_demo())
    assert plan.exclusion_envio == D("2000.00") and plan.gasto_computable == D("12000.00")


@pytest.mark.parametrize(
    "cambios",
    [{"subvencion_envio_aplicable": False}, {"electores_envio": None}],
)
def test_sin_requisitos_o_sin_electores_no_se_descuenta_nada(camp, cambios) -> None:
    esc, v = camp
    _con_envio(esc, v, **cambios)
    plan = construir_plan_campana(v, cfg_demo())
    assert plan.exclusion_envio == D("0.00") and plan.gasto_computable == plan.gasto_total


def test_con_la_subvencion_de_envio_sin_verificar_no_se_descuenta(camp) -> None:
    esc, v = camp
    _con_envio(esc, v)
    plan = construir_plan_campana(v, sin_verificar(cfg_demo(), "subvencion_envio_por_elector"))
    assert plan.exclusion_envio == D("0.00") and "pendiente de verificación" in plan.nota_envio


def test_el_envio_cambia_el_resultado_de_l004(camp) -> None:
    esc, v = camp
    linea(esc.tesorero(), v, "G.7.13", "12000", tipo="EXTRAORDINARIO")  # total 17.000 > 14.960
    proceso_electoral(esc.tesorero(), v, subvencion_envio_aplicable=True, electores_envio=60000)
    assert "L-004" not in {i.codigo for i in validar(v).incidencias}  # descuenta 12.000
    proceso_electoral(esc.tesorero(), v, subvencion_envio_aplicable=False)
    assert any("17.000,00" in m for m in msgs(validar(v), "L-004"))


# --------------------------------------------------------------------- L-012


def _aportacion(esc, v, n: int, importe: str):
    ln = linea(
        esc.tesorero(),
        v,
        "I.4.3",
        importe,
        confianza="BAJA",
        dimension="CAMPANA",
        tipo="EXTRAORDINARIO",
    )
    dn.registrar_donacion(esc.tesorero(), v, ln, donante(esc.tesorero(), n), D(importe))
    return ln


def test_l012_nadie_aporta_a_la_campana_mas_del_maximo(camp) -> None:
    esc, v = camp
    _aportacion(esc, v, 21, "1000")  # justo el máximo ficticio (1.000 €): se acepta
    assert "L-012" not in {i.codigo for i in validar(v).incidencias}
    _aportacion(esc, v, 21, "1")  # el mismo donante, 1 € más
    [m] = msgs(validar(v), "L-012")
    assert "1.001,00" in m and "1.000,00" in m


def test_l012_suma_todas_las_lineas_de_campana_del_donante(camp) -> None:
    esc, v = camp
    _aportacion(esc, v, 22, "600")
    _aportacion(esc, v, 22, "600")
    assert len(msgs(validar(v), "L-012")) == 1


def test_l012_ignora_las_donaciones_que_no_son_de_campana(camp) -> None:
    esc, v = camp
    ln = linea(esc.tesorero(), v, "I.4.1", "1400", confianza="BAJA")
    dn.registrar_donacion(esc.tesorero(), v, ln, donante(esc.tesorero(), 23), D("1400"))
    assert "L-012" not in {i.codigo for i in validar(v).incidencias}


def test_l012_con_el_parametro_sin_verificar_no_se_da_por_cumplida(camp) -> None:
    esc, v = camp
    _aportacion(esc, v, 24, "100")
    cfg = sin_verificar(cfg_demo(), "limite_aportacion_electoral_por_persona")
    assert any("pendiente de verificación" in m for m in msgs(validar(v, cfg), "L-012"))


# ---------------------------------------------------------------- L-013 / L-014


def test_l013_la_subvencion_no_supera_el_gasto(camp) -> None:
    esc, v = camp
    assert "L-013" not in {i.codigo for i in validar(v).incidencias}
    linea(
        esc.tesorero(),
        v,
        "I.3.4",
        "2000",
        dimension="CAMPANA",
        tipo="CONDICIONADO",
        confianza="BAJA",
    )  # 6.000 de subvención > 5.000 de gasto
    [i] = [x for x in validar(v).incidencias if x.codigo == "L-013"]
    assert i.gravedad == "AVISO" and "6.000,00" in i.mensaje


def test_l014_compara_con_la_subvencion_estimada(camp) -> None:
    esc, v = camp
    proceso_electoral(esc.tesorero(), v, concejales_previstos=10, votos_previstos=2000)
    plan = construir_plan_campana(v, cfg_demo())
    assert plan.subvencion_estimada == D("3000.00")  # 10 × 200 + 2.000 × 0,50
    [m] = msgs(validar(v), "L-014")  # subvención presupuestada: 4.000 > 3.000
    assert "3.000,00" in m
    proceso_electoral(esc.tesorero(), v, concejales_previstos=30, votos_previstos=2000)
    assert "L-014" not in {i.codigo for i in validar(v).incidencias}


def test_l014_no_se_evalua_sin_previsiones_y_avisa_si_el_parametro_no_esta_verificado(camp) -> None:
    esc, v = camp
    assert "L-014" not in {i.codigo for i in validar(v).incidencias}
    proceso_electoral(esc.tesorero(), v, concejales_previstos=10)
    res = validar(v, sin_verificar(cfg_demo(), "subvencion_electoral_por_concejal"))
    assert any("pendiente de verificación" in m for m in msgs(res, "L-014"))


def test_la_estimacion_suma_el_envio_cuando_aplica(camp) -> None:
    esc, v = camp
    proceso_electoral(
        esc.tesorero(),
        v,
        concejales_previstos=10,
        subvencion_envio_aplicable=True,
        electores_envio=1000,
    )
    assert construir_plan_campana(v, cfg_demo()).subvencion_estimada == D("2200.00")  # 2.000 + 200


# --------------------------------------------------------------------- L-015


def test_l015_gasto_fuera_del_periodo_electoral(camp) -> None:
    esc, v = camp  # el gasto de la prueba se reparte en los 12 meses
    proceso_electoral(
        esc.tesorero(),
        v,
        fecha_convocatoria=date(2070, 3, 1),
        fecha_elecciones=date(2070, 3, 26),
        fecha_proclamacion=date(2070, 4, 20),
    )
    [m] = msgs(validar(v), "L-015")
    meses = m.split("en: ")[1]
    assert "01/2070" in meses and "12/2070" in meses
    assert "03/2070" not in meses and "04/2070" not in meses
    proceso_electoral(
        esc.tesorero(),
        v,
        fecha_convocatoria=date(2070, 1, 5),
        fecha_elecciones=date(2070, 6, 1),
        fecha_proclamacion=date(2070, 12, 20),
    )
    assert "L-015" not in {i.codigo for i in validar(v).incidencias}


def test_l015_sin_fechas_no_se_evalua(camp) -> None:
    _, v = camp
    assert "L-015" not in {i.codigo for i in validar(v).incidencias}


# --------------------------------------------------------------------- V-011


def test_v011_avisa_al_acercarse_al_limite(camp) -> None:
    esc, v = camp
    assert "V-011" not in {i.codigo for i in validar(v).incidencias}  # 33 % < 90 %
    linea(esc.tesorero(), v, "G.7.3", "8500", tipo="EXTRAORDINARIO")  # 13.500 = 90,2 %
    [m] = msgs(validar(v), "V-011")
    assert "90.2 %" in m


def test_v011_sin_configurar_avisa_y_sin_gasto_calla(camp) -> None:
    esc, v = camp
    ParametrosAnexosCfg.objects.filter(es_demo=True).update(porcentaje_aviso_limite_campana=None)
    assert any("no está configurado" in m for m in msgs(validar(v), "V-011"))
    sin = version_valida(esc, 2071)
    assert "V-011" not in {i.codigo for i in validar(sin).incidencias}


def test_v011_deja_el_paso_a_l004_cuando_ya_se_supera(camp) -> None:
    esc, v = camp
    linea(esc.tesorero(), v, "G.7.3", "11000", tipo="EXTRAORDINARIO")
    codigos = {i.codigo for i in validar(v).incidencias}
    assert "L-004" in codigos and "V-011" not in codigos


# ------------------------------------------------------------------ calendario


def test_el_calendario_calcula_los_plazos_desde_los_parametros(camp) -> None:
    esc, v = camp
    proceso_electoral(
        esc.tesorero(),
        v,
        fecha_convocatoria=date(2070, 9, 1),
        fecha_elecciones=date(2070, 10, 1),
        fecha_proclamacion=date(2070, 10, 20),
    )
    hitos = {h.nombre: h for h in construir_plan_campana(v, cfg_demo()).calendario}
    solicitud = hitos["Solicitud del adelanto de la subvención"]
    assert (solicitud.desde, solicitud.hasta) == (date(2070, 9, 22), date(2070, 9, 24))
    assert hitos["El adelanto se pone a disposición a partir de"].desde == date(2070, 9, 30)
    conta = hitos["Presentación de la contabilidad electoral al Tribunal de Cuentas"]
    assert (conta.desde, conta.hasta) == (date(2071, 1, 9), date(2071, 2, 3))
    assert all(h.verificado for h in hitos.values())  # la demo los trae verificados


def test_con_los_parametros_reales_el_calendario_avisa_de_que_no_esta_verificado(camp) -> None:
    esc, v = camp
    proceso_electoral(
        esc.tesorero(), v, fecha_convocatoria=date(2070, 9, 1), fecha_elecciones=date(2070, 10, 1)
    )
    plan = construir_plan_campana(v, cargar_configuracion(False))
    assert plan.calendario and not any(h.verificado for h in plan.calendario[1:])
    assert plan.limite is None and "verificar" in plan.limite_pendiente[0]  # real: sin verificar


# ----------------------------------------------------- L-007 acotado por ámbito


def test_l007_no_exige_los_parametros_electorales_ni_los_informativos_sin_elecciones(esc) -> None:
    sin = version_valida(esc, 2072)
    res = validar_version(sin, cfg=cargar_configuracion(False), hoy=HOY)
    texto = " ".join(msgs(res, "L-007"))
    assert "gasto_electoral" not in texto and "subvencion_electoral" not in texto


def test_l007_con_elecciones_exige_los_electorales_pero_no_los_informativos(camp) -> None:
    _, v = camp
    res = validar_version(v, cfg=cargar_configuracion(False), hoy=HOY)
    texto = " ".join(msgs(res, "L-007"))
    assert "gasto_electoral_euros_por_habitante" in texto
    assert "limite_aportacion_electoral_por_persona" in texto
    assert "subvencion_electoral_por_voto" not in texto  # informativo: no condiciona
    assert "plazo_contabilidad_electoral_desde_dias" not in texto


# ----------------------------------------------------------------- el servicio


def test_el_proceso_lo_guarda_solo_el_tesorero_en_borrador_de_un_ejercicio_con_campana(
    camp,
) -> None:
    esc, v = camp
    with pytest.raises(PermissionDenied):
        an.guardar_proceso_electoral(esc.vocal(0), v, denominacion="x")
    sin = version_valida(esc, 2073)
    with pytest.raises(ValidationError, match="no tiene proceso electoral"):
        an.guardar_proceso_electoral(esc.tesorero(), sin, denominacion="x")
    proponer(esc, v)
    v.refresh_from_db()
    with pytest.raises(VersionNoEditable):
        an.guardar_proceso_electoral(esc.tesorero(), v, denominacion="x")


def test_las_fechas_deben_ir_en_orden(camp) -> None:
    esc, v = camp
    with pytest.raises(ValidationError, match="anterior a la convocatoria"):
        an.guardar_proceso_electoral(
            esc.tesorero(),
            v,
            fecha_convocatoria=date(2070, 5, 2),
            fecha_elecciones=date(2070, 5, 1),
        )
    with pytest.raises(ValidationError, match="proclamación"):
        an.guardar_proceso_electoral(
            esc.tesorero(),
            v,
            fecha_elecciones=date(2070, 5, 2),
            fecha_proclamacion=date(2070, 5, 1),
        )
    with pytest.raises(ValidationError, match="desconocidos"):
        an.guardar_proceso_electoral(esc.tesorero(), v, inventado=1)


def test_guardar_el_proceso_deja_auditoria(camp) -> None:
    esc, v = camp
    r = RegistroAuditoria.objects.filter(accion="campana.guardar_proceso_electoral").latest("id")
    assert dict(r.despues or {})["habitantes_derecho"] == "136000"
    proceso_electoral(esc.tesorero(), v, habitantes_derecho=140000)
    r = RegistroAuditoria.objects.filter(accion="campana.guardar_proceso_electoral").latest("id")
    assert dict(r.antes or {})["habitantes_derecho"] == "136000"


# --------------------------------------------------- huella, SQL y copias


def test_el_proceso_electoral_forma_parte_de_la_huella(camp) -> None:
    esc, v = camp
    antes = calcular_hash(v)
    proceso_electoral(esc.tesorero(), v, habitantes_derecho=140000)
    assert calcular_hash(v) != antes
    assert contenido_canonico(v)["campana"]["habitantes_derecho"] == 140000
    v.version_huella = 2  # con la huella antigua la campaña no cuenta
    assert "campana" not in contenido_canonico(v)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE anexos_procesoelectoral SET habitantes_derecho = 1 WHERE version_id = %s",
        "DELETE FROM anexos_procesoelectoral WHERE version_id = %s",
    ],
)
def test_el_proceso_de_una_version_sellada_no_se_toca_ni_con_sql(camp, sql) -> None:
    esc, v = camp
    proponer(esc, v)
    with pytest.raises(DatabaseError, match="solo lectura"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(sql, (v.pk,))


def test_una_modificacion_hereda_el_proceso_y_la_prorroga_no(esc) -> None:
    v = version_valida(esc, 2074, campana=True)
    aprobar_cp(esc, v)
    ratificar(esc, v)
    m = fs.crear_modificacion(esc.tesorero(), v, "Cambio de prueba")
    assert ProcesoElectoral.objects.get(version=m).habitantes_derecho == 136000
    from apps.presupuesto import servicios as ps

    ej, _ = ps.crear_ejercicio(esc.tesorero(), anio=2075, hay_proceso_electoral=True, es_demo=True)
    p = fs.crear_prorroga(esc.tesorero(), ej, hoy=date(2075, 1, 3))
    assert not ProcesoElectoral.objects.filter(version=p).exists()


# ------------------------------------------------------------- memoria y vistas


def test_la_memoria_pide_la_seccion_de_campana_solo_con_proceso_electoral(esc) -> None:
    sin = version_valida(esc, 2076)
    con = version_valida(esc, 2077, campana=True)
    claves_sin = [s.cfg.clave for s in construir_memoria(sin).secciones]
    claves_con = [s.cfg.clave for s in construir_memoria(con).secciones]
    assert "campana" not in claves_sin and claves_con[-1] == "campana"
    bloque = construir_memoria(con).secciones[-1].auto
    assert bloque.limite == D("14960.00")


def test_la_pantalla_de_campana(camp) -> None:
    from django.test import Client

    from tests.conftest import CLAVE

    esc, v = camp
    c = Client()
    assert c.login(username=esc.t.username, password=CLAVE)
    c.post("/rol/", {"rol": "TESORERO"})
    url = f"/presupuestos/version/{v.pk}/campana/"
    p = c.get(url).content.decode()
    assert "Límite de gasto" in p and "14.960,00" in p and "Calendario legal" in p
    assert "Guardar los datos" in p
    r = c.post(
        url,
        {
            "denominacion": "Elecciones nuevas",
            "habitantes_derecho": "150000",
            "provincias_adicional": "0",
            "fecha_convocatoria": "2070-08-25",
            "fecha_elecciones": "2070-09-26",
        },
    )
    assert r.status_code == 302
    assert ProcesoElectoral.objects.get(version=v).habitantes_derecho == 150000
    assert "16.500,00" in c.get(url).content.decode()  # 150.000 × 0,11
    sin = version_valida(esc, 2078)
    assert (
        "no tiene proceso electoral previsto"
        in c.get(f"/presupuestos/version/{sin.pk}/campana/").content.decode()
    )
    proponer(esc, v)
    assert "Guardar los datos" not in c.get(url).content.decode()


def test_la_comision_ve_la_campana_pero_no_la_edita(camp) -> None:
    from django.test import Client

    from tests.conftest import CLAVE

    esc, v = camp
    proponer(esc, v)
    c = Client()
    assert c.login(username=esc.cp[0].username, password=CLAVE)
    c.post("/rol/", {"rol": "COMISION_PERMANENTE"})
    p = c.get(f"/presupuestos/version/{v.pk}/campana/").content.decode()
    assert "Límite de gasto" in p and "Guardar los datos" not in p


def test_con_param_replace_no_rompe(camp) -> None:
    _, v = camp
    cfg = con_param(cfg_demo(), "gasto_electoral_euros_por_habitante", valor="0.10")
    assert construir_plan_campana(v, replace(cfg)).limite == D("13600.00")
    assert Linea.objects.filter(version=v).count() > 0
