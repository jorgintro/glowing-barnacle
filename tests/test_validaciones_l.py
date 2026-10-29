from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from apps.presupuesto import donantes as dn
from apps.presupuesto.configuracion import cargar_configuracion
from apps.presupuesto.models import Donante, Linea, Partida
from apps.validaciones.motor import validar_version
from tests.util_validaciones import (
    HOY,
    cfg_demo,
    codigos,
    con_param,
    donante,
    linea,
    presupuesto_valido,
    sin_verificar,
    validar,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def ok(borrador, ctx_tesorero):
    return borrador, ctx_tesorero, presupuesto_valido(ctx_tesorero, borrador)


def _mensajes(res, codigo: str) -> list[str]:
    return [i.mensaje for i in res.incidencias if i.codigo == codigo]


# ----------------------------------------------------------------------- L-001


def test_l001_cumple_con_donantes_identificados_y_bajo_el_limite(ok) -> None:
    version, _, _ = ok
    assert "L-001" not in codigos(validar(version))


def test_l001_donante_que_supera_el_limite_anual(ok) -> None:
    version, ctx, ls = ok
    c = Donante.objects.get(nombre="Donante 3")
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("2300.00"))
    dn.registrar_donacion(
        ctx, version, ls["dona"], c, Decimal("1000")
    )  # 600 + 1000 = 1.600 > 1.500
    msg = _mensajes(validar(version), "L-001")
    assert any("Donante 3" in m and "1.600,00" in m and "1.500,00" in m for m in msg)


def test_l001_el_limite_se_suma_entre_lineas_del_mismo_donante(ok) -> None:
    version, ctx, ls = ok
    otra = linea(ctx, version, "I.4.2", "1000", confianza="BAJA")
    c = Donante.objects.get(nombre="Donante 3")
    dn.registrar_donacion(ctx, version, otra, c, Decimal("1000"))  # 600 + 1000 en el año
    dn.registrar_donacion(
        ctx, version, otra, Donante.objects.get(nombre="Donante 4"), Decimal("0.01")
    )
    assert any("Donante 3" in m for m in _mensajes(validar(version), "L-001"))


def test_l001_persona_juridica_no_permitida(ok) -> None:
    version, ctx, ls = ok
    empresa = donante(ctx, 99, "JURIDICA", "Empresa Ficticia S. L.")
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("1100.00"))
    dn.registrar_donacion(ctx, version, ls["dona"], empresa, Decimal("100"))
    assert any(
        "Empresa Ficticia" in m and "jurídica" in m for m in _mensajes(validar(version), "L-001")
    )


def test_l001_persona_juridica_admitida_si_el_parametro_lo_permite(ok) -> None:
    version, ctx, ls = ok
    empresa = donante(ctx, 99, "JURIDICA")
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("1100.00"))
    dn.registrar_donacion(ctx, version, ls["dona"], empresa, Decimal("100"))
    cfg = con_param(cfg_demo(), "donaciones_personas_juridicas_permitidas", valor=True)
    assert "L-001" not in codigos(validar(version, cfg))


def test_l001_importe_sin_donante_identificado(ok) -> None:
    version, _, ls = ok
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("1250.00"))
    assert any(
        "250,00" in m and "sin donante identificado" in m
        for m in _mensajes(validar(version), "L-001")
    )


def test_l001_admite_anonimas_si_el_parametro_lo_permite(ok) -> None:
    version, _, ls = ok
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("1250.00"))
    cfg = con_param(cfg_demo(), "donaciones_anonimas_permitidas", valor=True)
    assert "L-001" not in codigos(validar(version, cfg))


def test_l001_identificadas_no_pueden_superar_la_linea(ok) -> None:
    version, _, ls = ok
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("900.00"))
    assert any("superan" in m for m in _mensajes(validar(version), "L-001"))


@pytest.mark.parametrize(
    "clave",
    [
        "limite_donacion_anual_por_donante",
        "donaciones_anonimas_permitidas",
        "donaciones_personas_juridicas_permitidas",
    ],
)
def test_l001_con_parametro_sin_verificar_no_se_da_por_cumplida(ok, clave: str) -> None:
    version, _, _ = ok
    msg = _mensajes(validar(version, sin_verificar(cfg_demo(), clave)), "L-001")
    assert len(msg) == 1 and clave in msg[0] and "pendiente de verificación" in msg[0]


def test_l001_no_aplica_sin_lineas_de_donaciones(borrador, ctx_tesorero) -> None:
    linea(ctx_tesorero, borrador, "I.1.1", "100", confianza="ALTA")
    cfg = sin_verificar(cfg_demo(), "limite_donacion_anual_por_donante")
    assert "L-001" not in codigos(validar(borrador, cfg))


# ----------------------------------------------------------------------- L-002


def test_l002_origen_prohibido_bloquea(ok) -> None:
    version, ctx, _ = ok
    ln = linea(
        ctx, version, "I.5.1", "100", confianza="BAJA", origen_ingreso="origen_prohibido_demo"
    )
    inc = [i for i in validar(version).incidencias if i.codigo == "L-002"]
    assert [i.linea for i in inc] == [ln.codigo]  # sin distinguir mayúsculas


def test_l002_origen_permitido_no_bloquea(ok) -> None:
    version, ctx, _ = ok
    linea(ctx, version, "I.5.1", "100", confianza="BAJA", origen_ingreso="VENTA_PROPIA")
    assert "L-002" not in codigos(validar(version))


def test_l002_lista_sin_verificar_no_se_da_por_cumplida(ok) -> None:
    version, _, _ = ok
    res = validar(version, sin_verificar(cfg_demo(), "fuentes_ingreso_prohibidas"))
    assert any("fuentes_ingreso_prohibidas" in m for m in _mensajes(res, "L-002"))


# ----------------------------------------------------------------------- L-003


def test_l003_aportaciones_identificadas_y_en_limite(ok) -> None:
    version, _, _ = ok
    assert "L-003" not in codigos(validar(version))


def test_l003_aportacion_sin_identificar(ok) -> None:
    version, _, ls = ok
    Linea.objects.filter(pk=ls["cargos"].pk).update(importe_anual=Decimal("2000.00"))
    assert any(
        "200,00" in m and "sin donante identificado" in m
        for m in _mensajes(validar(version), "L-003")
    )


def test_l003_aportante_que_supera_el_limite(ok) -> None:
    version, ctx, ls = ok
    a = Donante.objects.get(nombre="Donante 1")
    Linea.objects.filter(pk=ls["cargos"].pk).update(importe_anual=Decimal("2900.00"))
    dn.registrar_donacion(
        ctx, version, ls["cargos"], a, Decimal("1100")
    )  # 900 + 1100 = 2000 → límite
    assert "L-003" not in codigos(validar(version))
    Linea.objects.filter(pk=ls["cargos"].pk).update(importe_anual=Decimal("2901.00"))
    dn.registrar_donacion(ctx, version, ls["cargos"], a, Decimal("1"))  # 2001 > 2000
    assert any("Donante 1" in m for m in _mensajes(validar(version), "L-003"))


def test_l003_limite_sin_verificar(ok) -> None:
    version, _, _ = ok
    res = validar(version, sin_verificar(cfg_demo(), "limite_aportaciones_cargos_anual"))
    assert any("limite_aportaciones_cargos_anual" in m for m in _mensajes(res, "L-003"))


# ----------------------------------------------------------------------- L-004


@pytest.fixture
def con_campana(catalogo, ctx_tesorero):
    from apps.presupuesto import servicios as ps

    _, version = ps.crear_ejercicio(ctx_tesorero, anio=2051, hay_proceso_electoral=True)
    ls = presupuesto_valido(ctx_tesorero, version, campana=True)
    return version, ctx_tesorero, ls


def test_l004_dentro_del_limite(con_campana) -> None:
    version, _, _ = con_campana
    assert validar(version).incidencias == []


def test_l004_supera_el_limite(con_campana) -> None:
    version, ctx, _ = con_campana
    linea(ctx, version, "G.7.1", "10001", tipo="EXTRAORDINARIO")  # 5.000 + 10.001 > 15.000
    msg = _mensajes(validar(version), "L-004")
    assert len(msg) == 1 and "15.001,00" in msg[0] and "15.000,00" in msg[0]


def test_l004_justo_en_el_limite_se_acepta(con_campana) -> None:
    version, ctx, _ = con_campana
    linea(ctx, version, "G.7.1", "10000", tipo="EXTRAORDINARIO")
    assert "L-004" not in codigos(validar(version))


def test_l004_gasto_electoral_sin_proceso_electoral(ok) -> None:
    version, ctx, ls = ok
    version.ejercicio.hay_proceso_electoral = True
    version.ejercicio.save()
    linea(ctx, version, "G.7.1", "100")
    version.ejercicio.hay_proceso_electoral = False
    version.ejercicio.save()
    assert any("no tiene proceso electoral" in m for m in _mensajes(validar(version), "L-004"))


def test_l004_limite_sin_verificar(con_campana) -> None:
    version, _, _ = con_campana
    res = validar(version, sin_verificar(cfg_demo(), "limite_gasto_electoral"))
    assert any("limite_gasto_electoral" in m for m in _mensajes(res, "L-004"))


def test_l004_no_aplica_sin_campana_ni_gasto(ok) -> None:
    version, _, _ = ok
    assert "L-004" not in codigos(
        validar(version, sin_verificar(cfg_demo(), "limite_gasto_electoral"))
    )


# ----------------------------------------------------------------------- L-005


def test_l005_endeudamiento_dentro_del_limite_y_en_el_limite(ok) -> None:
    version, ctx, _ = ok
    for importe in ("0", "4999.99", "5000"):
        dn.guardar_resultado(
            ctx, version, explicacion="x", plan_financiacion="", endeudamiento=Decimal(importe)
        )
        assert "L-005" not in codigos(validar(version)), importe


def test_l005_endeudamiento_superior_al_limite(ok) -> None:
    version, ctx, _ = ok
    dn.guardar_resultado(
        ctx, version, explicacion="x", plan_financiacion="", endeudamiento=Decimal("5000.01")
    )
    msg = _mensajes(validar(version), "L-005")
    assert len(msg) == 1 and "5.000,01" in msg[0]


def test_l005_con_deuda_y_limite_sin_verificar(ok) -> None:
    version, ctx, _ = ok
    dn.guardar_resultado(
        ctx, version, explicacion="x", plan_financiacion="", endeudamiento=Decimal("100")
    )
    res = validar(version, sin_verificar(cfg_demo(), "limite_endeudamiento"))
    assert any("limite_endeudamiento" in m for m in _mensajes(res, "L-005"))


def test_l005_sin_deuda_no_necesita_el_parametro(ok) -> None:
    version, _, _ = ok
    assert "L-005" not in codigos(
        validar(version, sin_verificar(cfg_demo(), "limite_endeudamiento"))
    )


# ----------------------------------------------------------------------- L-006


def test_l006_cuadro_sin_validar_bloquea(ok) -> None:
    version, _, _ = ok
    cfg = cfg_demo()
    cfg = replace(cfg, cuadro=replace(cfg.cuadro, validado_por=None, fecha_validacion=None))
    msg = _mensajes(validar(version, cfg), "L-006")
    assert len(msg) == 1 and "pendiente de validación" in msg[0]


def test_l006_partida_fuera_del_cuadro(ok) -> None:
    version, _, ls = ok
    Partida.objects.filter(pk=ls["alquiler"].partida_id).update(activa=False)
    assert any("no figura en el cuadro" in m for m in _mensajes(validar(version), "L-006"))


def test_l006_cuenta_no_prevista_en_el_cuadro(ok) -> None:
    version, _, ls = ok
    from apps.presupuesto.models import CuentaPGC

    Linea.objects.filter(pk=ls["alquiler"].pk).update(
        cuenta_pgc=CuentaPGC.objects.get(codigo="640")
    )
    assert any("no está prevista" in m for m in _mensajes(validar(version), "L-006"))


def test_l006_cumple_con_el_cuadro_validado(ok) -> None:
    version, _, _ = ok
    assert "L-006" not in codigos(validar(version))


# ----------------------------------------------------------------------- L-007


def test_l007_todo_verificado_cumple(ok) -> None:
    version, _, _ = ok
    assert "L-007" not in codigos(validar(version))


def test_l007_parametro_pendiente_bloquea_y_lo_nombra(ok) -> None:
    version, _, _ = ok
    res = validar(version, sin_verificar(cfg_demo(), "limite_endeudamiento"))
    msg = _mensajes(res, "L-007")
    assert len(msg) == 1 and "limite_endeudamiento" in msg[0]


@pytest.mark.parametrize(
    "campo", ["valor", "referencia_normativa", "fecha_verificacion", "verificador"]
)
def test_l007_basta_con_que_falte_un_dato_de_la_verificacion(ok, campo: str) -> None:
    version, _, _ = ok
    vacio = {
        "valor": None,
        "referencia_normativa": "",
        "fecha_verificacion": None,
        "verificador": " ",
    }
    cfg = con_param(cfg_demo(), "limite_gasto_electoral", **{campo: vacio[campo]})
    assert "L-007" in codigos(validar(version, cfg))


def test_l007_fecha_futura(ok) -> None:
    version, _, _ = ok
    cfg = con_param(cfg_demo(), "limite_gasto_electoral", fecha_verificacion=date(2026, 10, 30))
    assert any("futura" in m for m in _mensajes(validar(version, cfg), "L-007"))


def test_l007_ventana_de_verificacion(ok) -> None:
    version, _, _ = ok  # el ejercicio de prueba es 2040
    cfg = cfg_demo()
    estricta = replace(cfg, internos=replace(cfg.internos, exigir_ventana_verificacion=True))
    assert any("no es vigente" in m for m in _mensajes(validar(version, estricta), "L-007"))
    for anio_ok in (2039, 2040):
        buena = con_param(
            estricta, "limite_gasto_electoral", fecha_verificacion=date(anio_ok, 1, 2)
        )
        todas = {
            k: replace(p, fecha_verificacion=date(anio_ok, 1, 2))
            for k, p in estricta.legales.items()
        }
        res = validar_version(version, cfg=replace(buena, legales=todas), hoy=date(2040, 12, 31))
        assert "L-007" not in codigos(res), anio_ok


# --------------------------------------------- con la configuración REAL (todo pendiente)


def test_con_la_configuracion_real_ninguna_version_puede_avanzar(ok) -> None:
    """Sin parámetros verificados ni cuadro validado, el sistema no da nada por cumplido."""
    version, _, _ = ok
    res = validar_version(version, cfg=cargar_configuracion(False), hoy=HOY)
    assert not res.puede_avanzar
    esperados = {"L-001", "L-002", "L-003", "L-006", "L-007"}
    assert esperados <= codigos(res)
    assert "L-007" in codigos(res) and len(_mensajes(res, "L-007")) == 7
