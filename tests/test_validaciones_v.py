from dataclasses import replace
from decimal import Decimal

import pytest

from apps.presupuesto import donantes as dn
from apps.presupuesto.models import CuentaPGC, Hipotesis, ImporteMensual, Linea
from apps.validaciones.contexto import construir_contexto
from apps.validaciones.reglas_v import v005
from apps.validaciones.tipos import Gravedad
from tests.util_validaciones import HOY, cfg_demo, codigos, linea, presupuesto_valido, validar

pytestmark = pytest.mark.django_db


@pytest.fixture
def ok(borrador, ctx_tesorero):
    return borrador, ctx_tesorero, presupuesto_valido(ctx_tesorero, borrador)


def test_el_presupuesto_valido_no_tiene_ninguna_incidencia(ok) -> None:
    version, _, _ = ok
    res = validar(version)
    assert res.incidencias == [], res.incidencias
    assert res.puede_avanzar
    assert set(res.superadas()) == set(res.reglas_ejecutadas) and len(res.reglas_ejecutadas) == 18


# ---------------------------------------------------------------- V-001 y V-002


def _romper_meses(ln: Linea) -> None:
    mes = ImporteMensual.objects.get(linea=ln, mes=12)
    ImporteMensual.objects.filter(pk=mes.pk).update(importe=mes.importe - Decimal("100.00"))


def test_v001_meses_que_no_suman_el_anual_bloquean(ok) -> None:
    version, _, ls = ok
    _romper_meses(ls["alquiler"])
    res = validar(version)
    inc = [i for i in res.incidencias if i.codigo == "V-001"]
    assert len(inc) == 1 and inc[0].linea == ls["alquiler"].codigo
    assert inc[0].gravedad == Gravedad.BLOQUEANTE and not res.puede_avanzar
    assert "4.700,00" in inc[0].mensaje and "4.800,00" in inc[0].mensaje


def test_v001_faltan_meses(ok) -> None:
    version, _, ls = ok
    ImporteMensual.objects.filter(linea=ls["alquiler"], mes=5).delete()  # queryset: sin guardia
    assert "V-001" in codigos(validar(version))


def test_v002_total_de_capitulo_descuadrado_bloquea(ok) -> None:
    version, _, ls = ok
    _romper_meses(ls["alquiler"])
    inc = [i for i in validar(version).incidencias if i.codigo == "V-002"]
    assert len(inc) == 1 and "G.2" in inc[0].mensaje


def test_v002_cuadra_si_todo_es_coherente(ok) -> None:
    version, _, _ = ok
    assert "V-002" not in codigos(validar(version))


# ----------------------------------------------------------------------- V-003


def test_v003_sin_cuenta(ok) -> None:
    version, _, ls = ok
    Linea.objects.filter(pk=ls["alquiler"].pk).update(cuenta_pgc=None)
    inc = [i for i in validar(version).incidencias if i.codigo == "V-003"]
    assert [i.linea for i in inc] == [ls["alquiler"].codigo]


def test_v003_cuenta_ajena_a_la_partida(ok) -> None:
    version, _, ls = ok
    Linea.objects.filter(pk=ls["personal"].pk).update(
        cuenta_pgc=CuentaPGC.objects.get(codigo="720")
    )
    inc = [i for i in validar(version).incidencias if i.codigo == "V-003"]
    assert len(inc) == 1 and "no corresponde" in inc[0].mensaje


def test_v003_cuenta_inactiva(ok) -> None:
    version, _, ls = ok
    CuentaPGC.objects.filter(pk=ls["alquiler"].cuenta_pgc_id).update(activa=False)
    assert any("ya no está activa" in i.mensaje for i in validar(version).incidencias)


# ----------------------------------------------------------------------- V-004


@pytest.mark.parametrize(
    ("campo", "texto"),
    [("hip_texto", "hipótesis"), ("hip_fuente", "fuente"), ("responsable", "responsable")],
)
def test_v004_falta_hipotesis_fuente_o_responsable(ok, campo: str, texto: str) -> None:
    version, _, ls = ok
    ln = ls["alquiler"]
    if campo == "hip_texto":
        Hipotesis.objects.filter(linea=ln).update(texto="  ")
    elif campo == "hip_fuente":
        Hipotesis.objects.filter(linea=ln).update(fuente="")
    else:
        Linea.objects.filter(pk=ln.pk).update(responsable="")
    inc = [i for i in validar(version).incidencias if i.codigo == "V-004"]
    assert len(inc) == 1 and texto in inc[0].mensaje.lower()


def test_v004_ingreso_sin_confianza(ok) -> None:
    version, _, ls = ok
    Hipotesis.objects.filter(linea=ls["cuotas"]).update(confianza="")
    inc = [i for i in validar(version).incidencias if i.codigo == "V-004"]
    assert len(inc) == 1 and "confianza" in inc[0].mensaje


# ----------------------------------------------------------------------- V-005


def test_v005_negativo_sin_justificar_en_un_mes(ok) -> None:
    version, _, ls = ok
    ImporteMensual.objects.filter(linea=ls["alquiler"], mes=1).update(importe=Decimal("-1.00"))
    assert "V-005" in codigos(validar(version))


def test_v005_ajuste_negativo_justificado_es_valido(ok) -> None:
    version, ctx, _ = ok
    linea(
        ctx, version, "G.5.1", "-50", es_ajuste=True, justificacion_ajuste="Devolución de comisión"
    )
    assert "V-005" not in codigos(validar(version))


def test_v005_ajuste_negativo_sin_justificar(ok) -> None:
    version, ctx, _ = ok
    ln = linea(ctx, version, "G.5.1", "-50", es_ajuste=True, justificacion_ajuste="Devolución")
    Linea.objects.filter(pk=ln.pk).update(justificacion_ajuste="")
    inc = [i for i in validar(version).incidencias if i.codigo == "V-005"]
    assert [i.linea for i in inc] == [ln.codigo]


def test_v005_mas_de_dos_decimales(ok) -> None:
    version, _, _ = ok
    ctx = construir_contexto(version, cfg=cfg_demo(), hoy=HOY)
    assert v005(ctx) == []
    ctx.lineas[0].importe_anual = Decimal("10.123")  # en memoria: la base de datos solo admite 2
    inc = v005(ctx)
    assert len(inc) == 1 and "decimales" in inc[0].mensaje


# ----------------------------------------------------------------------- V-006


def test_v006_falta_explicar_el_resultado(ok) -> None:
    version, ctx, _ = ok
    dn.guardar_resultado(
        ctx, version, explicacion="  ", plan_financiacion="", endeudamiento=Decimal("0")
    )
    inc = [i for i in validar(version).incidencias if i.codigo == "V-006"]
    assert len(inc) == 1 and "explicación" in inc[0].mensaje


def test_v006_deficit_sin_plan_bloquea_y_con_plan_se_acepta(ok) -> None:
    version, ctx, _ = ok
    linea(ctx, version, "G.3.4", "9000")  # lleva el resultado a déficit
    inc = [i for i in validar(version).incidencias if i.codigo == "V-006"]
    assert (
        len(inc) == 1 and "déficit" in inc[0].mensaje and "plan de financiación" in inc[0].mensaje
    )
    dn.guardar_resultado(
        ctx,
        version,
        explicacion="Déficit.",
        plan_financiacion="Aportación extraordinaria.",
        endeudamiento=Decimal("0"),
    )
    assert "V-006" not in codigos(validar(version))


# ----------------------------------------------------------------------- V-007


def test_v007_variacion_alta_sin_justificar_es_aviso_que_no_bloquea(ok) -> None:
    version, _, ls = ok
    Linea.objects.filter(pk=ls["alquiler"].pk).update(importe_ejercicio_anterior=Decimal("1000.00"))
    res = validar(version)
    inc = [i for i in res.incidencias if i.codigo == "V-007"]
    assert (
        len(inc) == 1
        and inc[0].gravedad == Gravedad.AVISO
        and inc[0].linea == ls["alquiler"].codigo
    )
    assert res.puede_avanzar  # solo un aviso


def test_v007_justificada_o_dentro_del_umbral_no_avisa(ok) -> None:
    version, _, ls = ok
    Linea.objects.filter(pk=ls["alquiler"].pk).update(
        importe_ejercicio_anterior=Decimal("1000.00"), justificacion_variacion="Nuevo local"
    )
    Linea.objects.filter(pk=ls["personal"].pk).update(importe_ejercicio_anterior=Decimal("2800.00"))
    assert "V-007" not in codigos(validar(version))  # 3000 sobre 2800 = 7,1 % < 25 %


def test_v007_anterior_cero(ok) -> None:
    version, _, ls = ok
    Linea.objects.filter(pk=ls["alquiler"].pk).update(importe_ejercicio_anterior=Decimal("0.00"))
    assert "V-007" in codigos(validar(version))


def test_v007_sin_umbral_configurado_avisa_que_no_se_puede_comprobar(ok) -> None:
    version, _, ls = ok
    Linea.objects.filter(pk=ls["alquiler"].pk).update(importe_ejercicio_anterior=Decimal("1000.00"))
    cfg = cfg_demo()
    cfg = replace(cfg, internos=replace(cfg.internos, umbral_variacion_porcentaje=None))
    res = validar(version, cfg)
    inc = [i for i in res.incidencias if i.codigo == "V-007"]
    assert (
        len(inc) == 1
        and "no está configurado" in inc[0].mensaje
        and inc[0].gravedad == Gravedad.AVISO
    )
