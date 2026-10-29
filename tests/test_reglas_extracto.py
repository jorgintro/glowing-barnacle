"""Reglas L-008 a L-011 y excepción de inmuebles de L-001 (extracto de la ley del Tesorero)."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from apps.presupuesto import donantes as dn
from apps.presupuesto.models import CuentaPGC, Donacion, Linea, TipoDonacion
from apps.validaciones.tipos import Gravedad
from tests.conftest import CLAVE
from tests.util_validaciones import (
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


def _msgs(res, codigo):
    return [i.mensaje for i in res.incidencias if i.codigo == codigo]


def _incs(res, codigo):
    return [i for i in res.incidencias if i.codigo == codigo]


# ----------------------------------------------------------------------- L-008 (aviso)


def test_l008_no_avisa_si_todo_esta_por_debajo_del_umbral(ok) -> None:
    version, _, _ = ok
    assert "L-008" not in codigos(validar(version))


def test_l008_donacion_superior_al_umbral_es_un_aviso_que_no_bloquea(ok) -> None:
    version, ctx, _ = ok
    ln = linea(ctx, version, "I.4.2", "3000.01", confianza="BAJA")
    dn.registrar_donacion(
        ctx, version, ln, donante(ctx, 20, nombre="Gran Donante"), Decimal("3000.01")
    )
    inc = _incs(validar(version), "L-008")
    assert len(inc) == 1 and inc[0].gravedad == Gravedad.AVISO and inc[0].linea == ln.codigo
    assert "Gran Donante" in inc[0].mensaje and "Tribunal de Cuentas" in inc[0].mensaje


def test_l008_justo_en_el_umbral_no_avisa_porque_la_ley_dice_superiores(ok) -> None:
    version, ctx, _ = ok
    ln = linea(ctx, version, "I.4.2", "3000", confianza="BAJA")
    dn.registrar_donacion(ctx, version, ln, donante(ctx, 20), Decimal("3000"))
    assert "L-008" not in codigos(validar(version))


def test_l008_las_donaciones_de_inmuebles_se_notifican_siempre(ok) -> None:
    version, ctx, _ = ok
    ln = linea(ctx, version, "I.4.2", "100", confianza="BAJA")
    dn.registrar_donacion(
        ctx, version, ln, donante(ctx, 20), Decimal("100"), tipo=TipoDonacion.ESPECIE_INMUEBLE
    )
    assert len(_incs(validar(version), "L-008")) == 1


def test_l008_las_aportaciones_se_suman_por_aportante(ok) -> None:
    version, ctx, _ = ok
    a = donante(ctx, 21, nombre="Cargo Acumulador")
    una = linea(ctx, version, "I.2.1", "2000", confianza="MEDIA")
    otra = linea(ctx, version, "I.2.1", "1000", confianza="MEDIA")
    dn.registrar_donacion(ctx, version, una, a, Decimal("2000"))
    dn.registrar_donacion(
        ctx, version, otra, a, Decimal("1000")
    )  # 3000: en el umbral, no lo supera
    assert "L-008" not in codigos(validar(version))
    dn.registrar_donacion(ctx, version, otra, a, Decimal("0.01"))  # 3000,01
    msg = _msgs(validar(version), "L-008")
    assert len(msg) == 1 and "Cargo Acumulador" in msg[0]


def test_l008_con_umbral_sin_verificar_avisa_de_que_no_puede_comprobar(ok) -> None:
    version, _, _ = ok
    res = validar(version, sin_verificar(cfg_demo(), "umbral_notificacion_tribunal_cuentas"))
    inc = _incs(res, "L-008")
    assert (
        len(inc) == 1
        and inc[0].gravedad == Gravedad.AVISO
        and "no se puede comprobar" in inc[0].mensaje.lower()
    )


def test_l008_no_aplica_sin_donaciones(borrador, ctx_tesorero) -> None:
    linea(ctx_tesorero, borrador, "I.1.1", "100", confianza="ALTA")
    res = validar(borrador, sin_verificar(cfg_demo(), "umbral_notificacion_tribunal_cuentas"))
    assert "L-008" not in codigos(res)


# ----------------------------------------------------------------------- L-009


def test_l009_linea_de_actividades_propias_sin_declarar_bloquea(ok) -> None:
    version, ctx, _ = ok
    ln = linea(ctx, version, "I.5.1", "400", confianza="MEDIA")
    inc = _incs(validar(version), "L-009")
    assert len(inc) == 1 and inc[0].linea == ln.codigo and inc[0].gravedad == Gravedad.BLOQUEANTE
    assert "Declara" in inc[0].mensaje and "150,00" in inc[0].mensaje


def test_l009_declarando_cero_cumple(ok) -> None:
    version, ctx, _ = ok
    linea(ctx, version, "I.5.1", "400", confianza="MEDIA", operaciones_altas=Decimal("0"))
    assert "L-009" not in codigos(validar(version))


def test_l009_operaciones_altas_sin_identificar_bloquean_y_identificadas_cumplen(ok) -> None:
    version, ctx, _ = ok
    ln = linea(ctx, version, "I.5.1", "400", confianza="MEDIA", operaciones_altas=Decimal("200"))
    msg = _msgs(validar(version), "L-009")
    assert len(msg) == 1 and "200,00" in msg[0] and "sin identificar" in msg[0]
    dn.registrar_donacion(ctx, version, ln, donante(ctx, 30), Decimal("120"))
    assert "80,00" in _msgs(validar(version), "L-009")[0]  # solo falta esa parte
    dn.registrar_donacion(ctx, version, ln, donante(ctx, 31), Decimal("80"))
    assert "L-009" not in codigos(validar(version))


def test_l009_una_linea_por_debajo_del_umbral_no_puede_contener_operaciones_altas(ok) -> None:
    version, ctx, _ = ok
    linea(ctx, version, "I.5.1", "149.99", confianza="MEDIA")  # sin declarar, pero < 150
    assert "L-009" not in codigos(validar(version))


def test_l009_con_umbral_sin_verificar_bloquea_si_hay_ingresos_de_actividades_propias(ok) -> None:
    version, ctx, _ = ok
    linea(ctx, version, "I.5.1", "10", confianza="MEDIA")
    res = validar(version, sin_verificar(cfg_demo(), "umbral_identificacion_actividades_propias"))
    assert any("umbral_identificacion_actividades_propias" in m for m in _msgs(res, "L-009"))


def test_l009_no_aplica_sin_lineas_de_i5(ok) -> None:
    version, _, _ = ok
    res = validar(version, sin_verificar(cfg_demo(), "umbral_identificacion_actividades_propias"))
    assert "L-009" not in codigos(res)


def test_operaciones_altas_solo_en_i5_y_dentro_del_importe(ok) -> None:
    version, ctx, _ = ok
    with pytest.raises(ValidationError, match="solo se declaran en I.5"):
        linea(ctx, version, "I.1.1", "100", confianza="ALTA", operaciones_altas=Decimal("10"))
    with pytest.raises(ValidationError, match="no pueden ser negativas ni superar"):
        linea(ctx, version, "I.5.1", "100", confianza="ALTA", operaciones_altas=Decimal("101"))
    with pytest.raises(ValidationError, match="no pueden ser negativas ni superar"):
        linea(ctx, version, "I.5.1", "100", confianza="ALTA", operaciones_altas=Decimal("-1"))


# ----------------------------------------------------------------------- L-010


def test_l010_donante_contratista_publico_bloquea(ok) -> None:
    version, ctx, ls = ok
    c = _contratista(ctx)
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("1100.00"))
    dn.registrar_donacion(ctx, version, ls["dona"], c, Decimal("100"))
    inc = _incs(validar(version), "L-010")
    assert (
        len(inc) == 1
        and "Contratista Ficticio" in inc[0].mensaje
        and inc[0].gravedad == Gravedad.BLOQUEANTE
    )


def _contratista(ctx, n=40):
    letra = "TRWAGMYFPDXBNJZSQVHLCKE"[n % 23]
    return dn.crear_donante(
        ctx, nombre="Contratista Ficticio", nif=f"{n:08d}{letra}", contratista_publico=True
    )


def test_l010_no_salta_con_donantes_normales_ni_si_el_parametro_lo_permite(ok) -> None:
    version, ctx, ls = ok
    assert "L-010" not in codigos(validar(version))
    c = _contratista(ctx)
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("1100.00"))
    dn.registrar_donacion(ctx, version, ls["dona"], c, Decimal("100"))
    permitido = con_param(cfg_demo(), "donaciones_contratistas_publicos_permitidas", valor=True)
    assert "L-010" not in codigos(validar(version, permitido))


def test_l010_con_parametro_sin_verificar_no_se_da_por_cumplida(ok) -> None:
    version, ctx, ls = ok
    c = _contratista(ctx)
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("1100.00"))
    dn.registrar_donacion(ctx, version, ls["dona"], c, Decimal("100"))
    res = validar(version, sin_verificar(cfg_demo(), "donaciones_contratistas_publicos_permitidas"))
    assert any("donaciones_contratistas_publicos_permitidas" in m for m in _msgs(res, "L-010"))


def test_l010_sin_contratistas_no_necesita_el_parametro(ok) -> None:
    version, _, _ = ok
    res = validar(version, sin_verificar(cfg_demo(), "donaciones_contratistas_publicos_permitidas"))
    assert "L-010" not in codigos(res)


# ----------------------------------------------------------------------- L-011


def _con_donacion(ok, **marcas):
    version, ctx, ls = ok
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("1100.00"))
    dn.registrar_donacion(
        ctx,
        version,
        ls["dona"],
        donante(ctx, 50, nombre="Donante Marcado"),
        Decimal("100"),
        **marcas,
    )
    return version


@pytest.mark.parametrize(
    ("marcas", "texto"),
    [
        ({"finalista": True}, "finalista"),
        ({"revocable": True}, "revocable"),
        ({"finalista": True, "revocable": True}, "finalista y revocable"),
    ],
)
def test_l011_donaciones_finalistas_o_revocables_bloquean(ok, marcas, texto) -> None:
    version = _con_donacion(ok, **marcas)
    msg = _msgs(validar(version), "L-011")
    assert len(msg) == 1 and "Donante Marcado" in msg[0] and texto in msg[0]


def test_l011_una_donacion_normal_no_salta(ok) -> None:
    version = _con_donacion(ok)
    assert "L-011" not in codigos(validar(version))


def test_l011_si_el_parametro_las_permite_no_salta(ok) -> None:
    version = _con_donacion(ok, finalista=True)
    cfg = con_param(cfg_demo(), "donaciones_finalistas_o_revocables_permitidas", valor=True)
    assert "L-011" not in codigos(validar(version, cfg))


def test_l011_con_parametro_sin_verificar_no_se_da_por_cumplida(ok) -> None:
    version = _con_donacion(ok, revocable=True)
    res = validar(
        version, sin_verificar(cfg_demo(), "donaciones_finalistas_o_revocables_permitidas")
    )
    assert any("donaciones_finalistas_o_revocables_permitidas" in m for m in _msgs(res, "L-011"))


def test_l011_una_donacion_anulada_deja_de_contar(ok) -> None:
    version = _con_donacion(ok, finalista=True)
    _, ctx, _ = ok
    dn.anular_donacion(ctx, Donacion.objects.get(finalista=True), "Se retira la condición")
    assert "L-011" not in codigos(validar(version))


# --------------------------------------------------- L-001: excepción de los inmuebles


def _dona_grande(ok, tipo):
    version, ctx, ls = ok
    d = donante(ctx, 60, nombre="Donante Grande")
    Linea.objects.filter(pk=ls["dona"].pk).update(importe_anual=Decimal("6000.00"))
    dn.registrar_donacion(ctx, version, ls["dona"], d, Decimal("5000"), tipo=tipo)
    return version


def test_l001_la_donacion_de_un_inmueble_no_cuenta_para_el_limite(ok) -> None:
    version = _dona_grande(ok, TipoDonacion.ESPECIE_INMUEBLE)  # 5.000 > 1.500, pero exenta
    assert "L-001" not in codigos(validar(version))


def test_l001_la_misma_cantidad_en_dinero_si_supera_el_limite(ok) -> None:
    version = _dona_grande(ok, TipoDonacion.DINERARIA)
    assert any("Donante Grande" in m for m in _msgs(validar(version), "L-001"))
    version2_msgs = _msgs(validar(version), "L-001")
    assert version2_msgs and "1.500,00" in version2_msgs[0]


def test_l001_una_donacion_en_especie_de_muebles_si_cuenta(ok) -> None:
    version = _dona_grande(ok, TipoDonacion.ESPECIE)
    assert any("Donante Grande" in m for m in _msgs(validar(version), "L-001"))


def test_l001_si_el_parametro_de_exencion_es_falso_el_inmueble_cuenta(ok) -> None:
    version = _dona_grande(ok, TipoDonacion.ESPECIE_INMUEBLE)
    cfg = con_param(cfg_demo(), "donaciones_inmuebles_exentas_de_limite", valor=False)
    assert any("Donante Grande" in m for m in _msgs(validar(version, cfg), "L-001"))


def test_l001_con_inmuebles_y_exencion_sin_verificar_no_se_da_por_cumplida(ok) -> None:
    version = _dona_grande(ok, TipoDonacion.ESPECIE_INMUEBLE)
    res = validar(version, sin_verificar(cfg_demo(), "donaciones_inmuebles_exentas_de_limite"))
    msg = _msgs(res, "L-001")
    assert any("donaciones_inmuebles_exentas_de_limite" in m for m in msg)
    assert any("Donante Grande" in m for m in msg)  # sin exención verificada, el inmueble cuenta


def test_l001_sin_inmuebles_no_necesita_el_parametro_de_exencion(ok) -> None:
    version, _, _ = ok
    res = validar(version, sin_verificar(cfg_demo(), "donaciones_inmuebles_exentas_de_limite"))
    assert "L-001" not in codigos(res)


# ------------------------------------------------------------ servicios, formularios y vistas


def test_donante_con_marca_de_contratista_y_donacion_con_sus_marcas(borrador, ctx_tesorero) -> None:
    c = _contratista(ctx_tesorero)
    assert c.contratista_publico is True and donante(ctx_tesorero, 70).contratista_publico is False
    ln = linea(ctx_tesorero, borrador, "I.4.1", "100", confianza="BAJA")
    d = dn.registrar_donacion(
        ctx_tesorero, borrador, ln, c, Decimal("10"), tipo="ESPECIE", finalista=True
    )
    assert (d.tipo, d.finalista, d.revocable) == ("ESPECIE", True, False)
    with pytest.raises(ValidationError, match="Tipo de donación"):
        dn.registrar_donacion(ctx_tesorero, borrador, ln, c, Decimal("10"), tipo="OTRO")


def test_se_pueden_registrar_transmitentes_en_ingresos_de_actividades_propias(
    borrador, ctx_tesorero
) -> None:
    ln = linea(
        ctx_tesorero, borrador, "I.5.1", "500", confianza="MEDIA", operaciones_altas=Decimal("500")
    )
    dn.registrar_donacion(ctx_tesorero, borrador, ln, donante(ctx_tesorero, 71), Decimal("500"))
    assert Donacion.objects.filter(linea=ln).count() == 1


def test_la_auditoria_de_donantes_sigue_sin_datos_personales(borrador, ctx_tesorero) -> None:
    from apps.auditoria.models import RegistroAuditoria

    c = _contratista(ctx_tesorero)
    reg = RegistroAuditoria.objects.get(accion="donante.crear", entidad_id=str(c.pk))
    assert "Contratista" not in str(reg.despues) and "contratista_publico" not in str(reg.despues)


def _cliente(usuario="tesorera") -> Client:
    c = Client()
    assert c.login(username=usuario, password=CLAVE)
    return c


def test_formularios_de_donante_y_donacion_con_los_campos_nuevos(
    borrador, ctx_tesorero, cliente_tesorero
) -> None:
    r = cliente_tesorero.post(
        "/donantes/",
        {
            "nombre": "Pablo Ficticio",
            "nif": "12345678Z",
            "tipo_persona": "FISICA",
            "contratista_publico": "on",
        },
    )
    assert r.status_code == 302
    from apps.presupuesto.models import Donante

    d = Donante.objects.get(nif="12345678Z")
    assert d.contratista_publico is True
    ln = linea(ctx_tesorero, borrador, "I.4.1", "500", confianza="BAJA")
    url = f"/presupuestos/version/{borrador.pk}/lineas/{ln.pk}/donantes/"
    pagina = cliente_tesorero.get(url).content.decode()
    assert "finalista" in pagina and "revocable" in pagina and "Tipo de donación" in pagina
    r = cliente_tesorero.post(
        url, {"donante": d.pk, "importe": "100,00", "tipo": "ESPECIE_INMUEBLE", "finalista": "on"}
    )
    assert r.status_code == 302
    don = Donacion.objects.get()
    assert (don.tipo, don.finalista, don.revocable) == ("ESPECIE_INMUEBLE", True, False)


def test_el_formulario_de_linea_pide_operaciones_altas_solo_en_i5(
    borrador, cliente_tesorero
) -> None:
    base = f"/presupuestos/version/{borrador.pk}/lineas/nueva/"
    assert (
        "operaciones individuales altas" in cliente_tesorero.get(base + "I.5.1/").content.decode()
    )
    for otra in ("I.1.1", "I.4.1", "G.2.1"):
        assert (
            "operaciones individuales altas"
            not in cliente_tesorero.get(base + otra + "/").content.decode()
        )


def test_operaciones_altas_se_guardan_desde_la_interfaz(borrador, cliente_tesorero) -> None:
    datos = {
        "denominacion": "Venta de entradas",
        "cuenta": CuentaPGC.objects.get(codigo="70x").pk,
        "importe_anual": "500,00",
        "tipo": "RECURRENTE",
        "dimension": "ORDINARIO",
        "responsable": "Tesorería",
        "hipotesis_texto": "h",
        "hipotesis_fuente": "f",
        "confianza": "MEDIA",
        "operaciones_altas": "200,00",
        "reparto": "UNIFORME",
    }
    r = cliente_tesorero.post(f"/presupuestos/version/{borrador.pk}/lineas/nueva/I.5.1/", datos)
    assert r.status_code == 302
    assert Linea.objects.get().operaciones_altas == Decimal("200.00")
    r = cliente_tesorero.post(
        f"/presupuestos/version/{borrador.pk}/lineas/nueva/I.5.1/",
        {**datos, "operaciones_altas": "9.999,00"},
    )
    assert r.status_code == 200 and Linea.objects.count() == 1  # supera el importe: se rechaza
