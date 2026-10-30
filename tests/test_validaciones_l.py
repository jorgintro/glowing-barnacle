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

    ejercicio, _ = ps.crear_ejercicio(ctx_tesorero, anio=2051, hay_proceso_electoral=True)
    version = ps.crear_presupuesto_electoral(ctx_tesorero, ejercicio)
    ls = presupuesto_valido(ctx_tesorero, version)
    return version, ctx_tesorero, ls


def test_l004_dentro_del_limite(con_campana) -> None:
    version, _, _ = con_campana
    assert validar(version).incidencias == []


def test_l004_supera_el_limite(con_campana) -> None:
    version, ctx, _ = con_campana
    linea(ctx, version, "G.7.1", "10000", tipo="EXTRAORDINARIO")  # 5.000 + 10.000 > 14.960
    msg = _mensajes(validar(version), "L-004")
    assert len(msg) == 1 and "15.000,00" in msg[0] and "14.960,00" in msg[0]


def test_l004_justo_en_el_limite_se_acepta(con_campana) -> None:
    version, ctx, _ = con_campana
    linea(ctx, version, "G.7.1", "9960", tipo="EXTRAORDINARIO")  # 5.000 + 9.960 = 14.960
    assert "L-004" not in codigos(validar(version))


def test_l004_no_se_evalua_en_el_presupuesto_ordinario(ok) -> None:
    version, _, _ = ok
    assert version.ambito == "ORDINARIO" and "L-004" not in codigos(validar(version))


def test_l004_limite_sin_verificar(con_campana) -> None:
    version, _, _ = con_campana
    res = validar(version, sin_verificar(cfg_demo(), "gasto_electoral_euros_por_habitante"))
    assert any("gasto_electoral_euros_por_habitante" in m for m in _mensajes(res, "L-004"))


def test_l004_no_aplica_sin_campana_ni_gasto(ok) -> None:
    version, _, _ = ok
    assert "L-004" not in codigos(
        validar(version, sin_verificar(cfg_demo(), "gasto_electoral_euros_por_habitante"))
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
    cfg = con_param(cfg_demo(), "limite_endeudamiento", **{campo: vacio[campo]})
    assert "L-007" in codigos(validar(version, cfg))


def test_l007_fecha_futura(ok) -> None:
    version, _, _ = ok
    cfg = con_param(cfg_demo(), "limite_endeudamiento", fecha_verificacion=date(2026, 10, 30))
    assert any("futura" in m for m in _mensajes(validar(version, cfg), "L-007"))


def test_l007_ventana_de_verificacion(ok) -> None:
    version, _, _ = ok  # el ejercicio de prueba es 2040
    cfg = cfg_demo()
    estricta = replace(cfg, internos=replace(cfg.internos, exigir_ventana_verificacion=True))
    assert any("no es vigente" in m for m in _mensajes(validar(version, estricta), "L-007"))
    for anio_ok in (2039, 2040):
        buena = con_param(estricta, "limite_endeudamiento", fecha_verificacion=date(anio_ok, 1, 2))
        todas = {
            k: replace(p, fecha_verificacion=date(anio_ok, 1, 2))
            for k, p in estricta.legales.items()
        }
        res = validar_version(version, cfg=replace(buena, legales=todas), hoy=date(2040, 12, 31))
        assert "L-007" not in codigos(res), anio_ok


# --------------------------------------------- con la configuración REAL (todo pendiente)


def test_con_la_configuracion_real_ninguna_version_puede_avanzar(ok) -> None:
    """Con parámetros sin verificar y el cuadro sin validar, el sistema no da nada por cumplido."""
    version, _, _ = ok
    res = validar_version(version, cfg=cargar_configuracion(False), hoy=HOY)
    assert not res.puede_avanzar
    assert {"L-003", "L-006", "L-007"} <= codigos(res)
    # Sin proceso electoral no se exigen los 16 parámetros electorales ni los informativos:
    # 2 sin valor y 9 verificados en 2026, que no valen para un ejercicio de 2040
    mensajes = _mensajes(res, "L-007")
    assert sum("pendiente de verificación" in m for m in mensajes) == 2
    assert sum("no es vigente" in m for m in mensajes) == 9


def test_los_parametros_declarados_verificados_ya_se_aplican_en_la_configuracion_real(ok) -> None:
    version, ctx, ls = ok
    real = cargar_configuracion(False)
    res = validar_version(version, cfg=real, hoy=HOY)
    assert "L-001" not in codigos(res)  # los 3 parámetros de L-001 figuran como verificados
    assert "L-002" not in codigos(res)
    # y se aplican de verdad: una persona jurídica se rechaza con la configuración real
    empresa = donante(ctx, 99, "JURIDICA", "Empresa Ficticia")
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("1100.00"))
    dn.registrar_donacion(ctx, version, ls["dona"], empresa, Decimal("100"))
    assert any(
        "jurídica" in m for m in _mensajes(validar_version(version, cfg=real, hoy=HOY), "L-001")
    )


# ------------------------- con los valores reales del extracto, una vez firmados por el Tesorero


def _real_firmado(*claves: str):
    """Configuración REAL con la firma del Tesorero (solo en la prueba) en algunos parámetros."""
    from tests.util_validaciones import con_param

    cfg = cargar_configuracion(False)
    for c in claves:
        cfg = con_param(
            cfg, c, fecha_verificacion=date(2026, 10, 29), verificador="Tesorero (prueba)"
        )
    return cfg


def test_si_se_quita_la_verificacion_los_valores_reales_dejan_de_bastar(ok) -> None:
    version, _, _ = ok
    cfg = sin_verificar(cargar_configuracion(False), "limite_donacion_anual_por_donante")
    res = validar_version(version, cfg=cfg, hoy=HOY)
    assert any("pendiente de verificación" in m for m in _mensajes(res, "L-001"))


def test_con_los_valores_reales_firmados_l001_aplica_50000_euros_y_prohibe_juridicas(ok) -> None:
    version, ctx, ls = ok
    cfg = _real_firmado(
        "limite_donacion_anual_por_donante",
        "donaciones_anonimas_permitidas",
        "donaciones_personas_juridicas_permitidas",
    )
    assert "L-001" not in codigos(validar_version(version, cfg=cfg, hoy=HOY))
    grande = donante(ctx, 50, nombre="Gran Donante Ficticio")
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("51000.00"))
    dn.registrar_donacion(ctx, version, ls["dona"], grande, Decimal("50001"))
    msg = _mensajes(validar_version(version, cfg=cfg, hoy=HOY), "L-001")
    assert any("Gran Donante" in m and "50.000,00" in m for m in msg)
    empresa = donante(ctx, 51, "JURIDICA", "Empresa Ficticia")
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("51100.00"))
    dn.registrar_donacion(ctx, version, ls["dona"], empresa, Decimal("100"))
    assert any(
        "jurídica" in m for m in _mensajes(validar_version(version, cfg=cfg, hoy=HOY), "L-001")
    )


def test_con_la_lista_real_firmada_l002_bloquea_actividad_mercantil(ok) -> None:
    version, ctx, _ = ok
    cfg = _real_firmado("fuentes_ingreso_prohibidas")
    ln = linea(ctx, version, "I.5.1", "100", confianza="BAJA", origen_ingreso="actividad_mercantil")
    inc = [i for i in validar_version(version, cfg=cfg, hoy=HOY).incidencias if i.codigo == "L-002"]
    assert [i.linea for i in inc] == [ln.codigo]
