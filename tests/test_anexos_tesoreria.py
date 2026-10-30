"""Plan de tesorería (V-009, V-010), escenarios y alertas."""

from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied

from apps.anexos import servicios as an
from apps.anexos.configuracion import parametros_actuales
from apps.anexos.models import ParametrosAnexosCfg
from apps.anexos.tesoreria import AJUSTADO, BASE, PRUDENTE, calcular_plan
from apps.presupuesto.errores import VersionNoEditable
from apps.presupuesto.models import ImporteMensual, Linea
from apps.validaciones.motor import validar_version
from tests.util_flujo import crear_escenario, proponer, version_valida
from tests.util_validaciones import HOY, cfg_demo

pytestmark = pytest.mark.django_db


@pytest.fixture
def esc(catalogo):
    return crear_escenario()


def avisos(version, codigo: str):
    res = validar_version(version, cfg=cfg_demo(), hoy=HOY)
    return [i for i in res.incidencias if i.codigo == codigo]


def D(x: str) -> Decimal:
    return Decimal(x)


def test_el_plan_base_suma_cobros_y_pagos_mes_a_mes(esc) -> None:
    v = version_valida(esc)
    plan = calcular_plan(v)
    base = plan.escenario(BASE)
    assert len(base.meses) == 12
    assert base.total_cobros == D("11800") and base.total_pagos == D("7800")
    assert sum((m.flujo for m in base.meses), D("0")) == D("4000")
    assert base.saldo_final == D("104000")  # 100.000 de saldo inicial + 4.000 de resultado
    # el saldo de cada mes es el anterior más el flujo neto
    saldo = plan.saldo_inicial
    assert saldo is not None
    for m in base.meses:
        saldo += m.flujo
        assert m.saldo == saldo


def test_sin_saldo_inicial_hay_flujo_pero_no_saldos(esc) -> None:
    v = version_valida(esc)
    an.guardar_saldo_inicial(esc.tesorero(), v, None)
    base = calcular_plan(v).escenario(BASE)
    assert base.total_cobros == D("11800") and all(m.saldo is None for m in base.meses)
    assert base.saldo_final is None and base.meses_en_tension == []
    [aviso] = avisos(v, "V-009")
    assert aviso.gravedad == "AVISO" and "saldo inicial" in aviso.mensaje
    assert avisos(v, "V-010") == []  # sin saldos no hay nada que comprobar


def test_un_saldo_negativo_o_bajo_el_minimo_es_tension(esc) -> None:
    v = version_valida(esc)
    # Se concentra todo el gasto en enero para forzar la tensión.
    gasto = Linea.objects.get(version=v, partida__codigo="G.2.1")
    ImporteMensual.objects.filter(linea=gasto).update(importe=D("0"))
    ImporteMensual.objects.filter(linea=gasto, mes=1).update(importe=gasto.importe_anual)
    an.guardar_saldo_inicial(esc.tesorero(), v, D("100"))
    base = calcular_plan(v).escenario(BASE)
    enero = base.meses[0]
    assert enero.en_tension and enero.motivo_tension in (
        "saldo negativo",
        "saldo por debajo del mínimo",
    )
    mensajes = [i.mensaje for i in avisos(v, "V-010")]
    assert any("enero" in m for m in mensajes)


def test_por_debajo_del_minimo_pero_positivo(esc) -> None:
    v = version_valida(esc)
    an.guardar_saldo_inicial(esc.tesorero(), v, D("100"))
    base = calcular_plan(v).escenario(BASE)
    positivos_bajos = [m for m in base.meses if m.saldo is not None and 0 <= m.saldo < D("500")]
    for m in positivos_bajos:
        assert m.motivo_tension == "saldo por debajo del mínimo"


def test_sin_saldo_minimo_solo_se_avisa_de_que_no_se_puede_comprobar_todo(esc) -> None:
    v = version_valida(esc)
    ParametrosAnexosCfg.objects.filter(es_demo=True).update(saldo_minimo_tesoreria=None)
    [aviso] = avisos(v, "V-010")
    assert "no está configurado" in aviso.mensaje


def test_el_escenario_prudente_descuenta_ingresos_segun_la_confianza(esc) -> None:
    v = version_valida(esc)
    # demo: ALTA 5 %, MEDIA 15 %, BAJA 40 %. Cuotas 6000 (alta), cargos 1800 y subv 3000 (media),
    # donaciones 1000 (baja).
    esperado = D("6000") * D("0.95") + D("4800") * D("0.85") + D("1000") * D("0.60")
    prudente = calcular_plan(v).escenario(PRUDENTE)
    assert prudente.configurado
    assert abs(prudente.total_cobros - esperado) <= D("0.12")  # redondeo de céntimos por mes
    assert prudente.total_pagos == D("7800")


def test_el_escenario_ajustado_descuenta_gastos_segun_el_tipo(esc) -> None:
    v = version_valida(esc)
    # demo: RECURRENTE 5 %. Las dos líneas de gasto de la prueba son recurrentes.
    ajustado = calcular_plan(v).escenario(AJUSTADO)
    assert abs(ajustado.total_pagos - D("7800") * D("0.95")) <= D("0.12")
    assert ajustado.total_cobros == D("11800")


def test_un_escenario_sin_porcentajes_no_se_calcula(esc) -> None:
    v = version_valida(esc)
    ParametrosAnexosCfg.objects.filter(es_demo=True).update(
        reduccion_ingresos_alta=None,
        reduccion_ingresos_media=None,
        reduccion_ingresos_baja=None,
    )
    prudente = calcular_plan(v).escenario(PRUDENTE)
    assert not prudente.configurado and prudente.meses == [] and prudente.saldo_final is None


def test_los_importes_no_pierden_centimos_en_el_escenario_base(esc) -> None:
    v = version_valida(esc)
    suma = sum((m.importe for m in ImporteMensual.objects.filter(linea__version=v)), D("0"))
    base = calcular_plan(v).escenario(BASE)
    assert base.total_cobros + base.total_pagos == suma


# ------------------------------------------------------------ permisos y sellado


def test_el_saldo_inicial_lo_pone_solo_el_tesorero_y_solo_en_borrador(esc) -> None:
    v = version_valida(esc)
    with pytest.raises(PermissionDenied):
        an.guardar_saldo_inicial(esc.vocal(0), v, D("1"))
    proponer(esc, v)
    v.refresh_from_db()
    with pytest.raises(VersionNoEditable):
        an.guardar_saldo_inicial(esc.tesorero(), v, D("1"))


def test_el_saldo_se_redondea_a_centimos_y_queda_en_la_auditoria(esc) -> None:
    from apps.auditoria.models import RegistroAuditoria

    v = version_valida(esc)
    an.guardar_saldo_inicial(esc.tesorero(), v, D("1234.567"))
    v.refresh_from_db()
    assert v.saldo_inicial_tesoreria == D("1234.57")
    r = RegistroAuditoria.objects.filter(accion="tesoreria.guardar_saldo_inicial").latest("id")
    assert r.despues == {"saldo_inicial": "1234.57"}


def test_la_version_sellada_se_muestra_con_los_porcentajes_con_que_se_sello(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    antes = calcular_plan(v).escenario(PRUDENTE).total_cobros
    ParametrosAnexosCfg.objects.filter(es_demo=True).update(reduccion_ingresos_baja=D("90"))
    v.refresh_from_db()
    assert calcular_plan(v).escenario(PRUDENTE).total_cobros == antes
    assert parametros_actuales(True).reduccion_ingresos["BAJA"] == D("90")
    nuevo = version_valida(esc, 2066)
    assert (
        calcular_plan(nuevo).escenario(PRUDENTE).total_cobros < antes
    )  # el borrador usa lo actual
