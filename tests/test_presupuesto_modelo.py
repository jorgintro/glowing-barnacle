from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.servicios import Contexto
from apps.presupuesto import servicios as ps
from apps.presupuesto.calculos import resumen_version
from apps.presupuesto.errores import RegistroNoBorrable, VersionNoEditable
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import CuentaPGC, Hipotesis, ImporteMensual, Linea, Partida
from apps.usuarios.roles import Rol
from tests.conftest import crear, poner_estado

pytestmark = pytest.mark.django_db
HIP = ps.DatosHipotesis("Cuota media por afiliado", "Padrón de afiliados", "ALTA")


def _linea(ctx: Contexto, version, partida: str = "I.1.1", importe: str = "1200", **extra):
    p = Partida.objects.get(codigo=partida)
    return ps.guardar_linea(
        ctx,
        version,
        partida=p,
        denominacion=extra.pop("denominacion", "Línea de prueba"),
        cuenta=p.cuentas.first() or CuentaPGC.objects.get(codigo="720"),
        importe_anual=Decimal(importe),
        hipotesis=HIP,
        responsable="Tesorería",
        **extra,
    )


def test_crear_ejercicio_crea_borrador_v1_y_audita(catalogo: None, ctx_tesorero: Contexto) -> None:
    ej, v = ps.crear_ejercicio(ctx_tesorero, anio=2041, hay_proceso_electoral=True)
    assert v.numero == 1 and v.estado == EstadoVersion.BORRADOR and v.editable
    assert RegistroAuditoria.objects.filter(
        accion="ejercicio.crear", entidad_id=str(ej.pk)
    ).exists()


def test_no_se_repite_ejercicio_ni_se_crea_sin_ser_tesorero(
    catalogo: None, ctx_tesorero: Contexto
) -> None:
    ps.crear_ejercicio(ctx_tesorero, anio=2042)
    with pytest.raises(ValidationError):
        ps.crear_ejercicio(ctx_tesorero, anio=2042)
    cp = crear("cp", Rol.COMISION_PERMANENTE)
    with pytest.raises(PermissionDenied):
        ps.crear_ejercicio(Contexto(cp, Rol.COMISION_PERMANENTE), anio=2043)


def test_linea_con_reparto_uniforme_y_hipotesis(borrador, ctx_tesorero: Contexto) -> None:
    linea = _linea(ctx_tesorero, borrador, importe="1200")
    assert linea.codigo == "I.1.1.01"
    assert [i.importe for i in linea.importes_mensuales.all()] == [Decimal("100.00")] * 12
    assert linea.hipotesis.fuente == "Padrón de afiliados"
    assert _linea(ctx_tesorero, borrador).codigo == "I.1.1.02"


def test_distribucion_mensual_manual_debe_sumar_el_anual(borrador, ctx_tesorero: Contexto) -> None:
    mal = [Decimal("10")] * 12
    with pytest.raises(ValidationError, match="no coincide"):
        _linea(ctx_tesorero, borrador, importe="100", mensual=mal)
    bien = [Decimal("0")] * 11 + [Decimal("100")]
    linea = _linea(ctx_tesorero, borrador, importe="100", mensual=bien)
    assert linea.importes_mensuales.get(mes=12).importe == Decimal("100.00")


@pytest.mark.parametrize(
    "cambio",
    [
        {"denominacion": " "},
        {"importe": "-5"},
    ],
)
def test_datos_incorrectos_se_rechazan(borrador, ctx_tesorero: Contexto, cambio) -> None:
    with pytest.raises(ValidationError):
        _linea(ctx_tesorero, borrador, **cambio)


def test_hipotesis_y_responsable_son_obligatorios(borrador, ctx_tesorero: Contexto) -> None:
    p = Partida.objects.get(codigo="I.1.1")
    base: dict[str, Any] = {
        "partida": p,
        "denominacion": "X",
        "cuenta": p.cuentas.first(),
        "importe_anual": Decimal("10"),
    }
    with pytest.raises(ValidationError):
        ps.guardar_linea(
            ctx_tesorero, borrador, hipotesis=ps.DatosHipotesis("", ""), responsable="A", **base
        )
    with pytest.raises(ValidationError):
        ps.guardar_linea(ctx_tesorero, borrador, hipotesis=HIP, responsable="", **base)


def test_cuenta_ajena_a_la_partida_se_rechaza(borrador, ctx_tesorero: Contexto) -> None:
    p = Partida.objects.get(codigo="I.1.1")
    with pytest.raises(ValidationError, match="no corresponde"):
        ps.guardar_linea(
            ctx_tesorero,
            borrador,
            partida=p,
            denominacion="X",
            cuenta=CuentaPGC.objects.get(codigo="640"),
            importe_anual=Decimal("10"),
            hipotesis=HIP,
            responsable="A",
        )


def test_importe_negativo_solo_como_ajuste_justificado(borrador, ctx_tesorero: Contexto) -> None:
    with pytest.raises(ValidationError):
        _linea(ctx_tesorero, borrador, importe="-50", es_ajuste=True)
    linea = _linea(
        ctx_tesorero, borrador, importe="-50", es_ajuste=True, justificacion_ajuste="Devolución"
    )
    assert linea.importe_anual == Decimal("-50.00")


def test_capitulo_electoral_solo_con_proceso_electoral(borrador, ctx_tesorero: Contexto) -> None:
    with pytest.raises(ValidationError, match="proceso electoral"):
        _linea(ctx_tesorero, borrador, partida="G.7.1")
    borrador.ejercicio.hay_proceso_electoral = True
    borrador.ejercicio.save()
    assert _linea(ctx_tesorero, borrador, partida="G.7.1").dimension == "CAMPANA"


def test_modificar_guarda_antes_y_despues(borrador, ctx_tesorero: Contexto) -> None:
    linea = _linea(ctx_tesorero, borrador, importe="1200")
    _linea(ctx_tesorero, borrador, importe="2400", linea=linea)
    reg = RegistroAuditoria.objects.get(accion="linea.modificar")
    assert reg.antes is not None and reg.despues is not None
    assert reg.antes["importe_anual"] == "1200.00" and reg.despues["importe_anual"] == "2400.00"
    assert reg.rol_activo == Rol.TESORERO


def test_anular_exige_motivo_no_borra_y_deja_de_sumar(borrador, ctx_tesorero: Contexto) -> None:
    linea = _linea(ctx_tesorero, borrador, importe="1200")
    with pytest.raises(ValidationError):
        ps.anular_linea(ctx_tesorero, linea, " ")
    ps.anular_linea(ctx_tesorero, linea, "Duplicada")
    linea.refresh_from_db()
    assert linea.anulada and Linea.objects.filter(pk=linea.pk).exists()
    assert resumen_version(borrador).ingresos == Decimal("0.00")
    assert RegistroAuditoria.objects.filter(accion="linea.anular", motivo="Duplicada").exists()
    with pytest.raises(ValidationError):  # una anulada ya no se edita
        _linea(ctx_tesorero, borrador, linea=linea)


@pytest.mark.parametrize("estado", [e for e in EstadoVersion if e != EstadoVersion.BORRADOR])
def test_versiones_que_no_son_borrador_no_admiten_cambios(
    borrador,
    ctx_tesorero: Contexto,
    estado,
) -> None:
    linea = _linea(ctx_tesorero, borrador)
    poner_estado(borrador, estado)
    with pytest.raises(VersionNoEditable):
        _linea(ctx_tesorero, borrador)
    with pytest.raises(VersionNoEditable):
        _linea(ctx_tesorero, borrador, linea=linea)
    with pytest.raises(VersionNoEditable):
        ps.anular_linea(ctx_tesorero, linea, "motivo")
    with pytest.raises(VersionNoEditable):
        linea.denominacion = "otra"
        linea.save()
    with pytest.raises(VersionNoEditable):
        ImporteMensual.objects.get(linea=linea, mes=1).save()
    with pytest.raises(VersionNoEditable):
        Hipotesis.objects.get(linea=linea).save()


def test_los_registros_no_se_borran(borrador, ctx_tesorero: Contexto) -> None:
    linea = _linea(ctx_tesorero, borrador)
    with pytest.raises(RegistroNoBorrable):
        linea.delete()
    with pytest.raises(RegistroNoBorrable):
        linea.hipotesis.delete()
    with pytest.raises(RegistroNoBorrable):
        linea.importes_mensuales.first().delete()  # type: ignore[union-attr]


def test_la_base_de_datos_rechaza_importes_negativos_sin_ajuste(borrador) -> None:
    p = Partida.objects.get(codigo="I.1.1")
    with pytest.raises(IntegrityError), transaction.atomic():
        Linea.objects.create(
            version=borrador, partida=p, codigo="X.1", denominacion="x", importe_anual=Decimal("-1")
        )


def test_totales_resultado_y_mensual(borrador, ctx_tesorero: Contexto) -> None:
    _linea(ctx_tesorero, borrador, "I.1.1", "1200")
    _linea(ctx_tesorero, borrador, "I.3.1", "600")
    _linea(ctx_tesorero, borrador, "G.2.1", "2400")
    r = resumen_version(borrador)
    assert r.ingresos == Decimal("1800.00") and r.gastos == Decimal("2400.00")
    assert r.resultado == Decimal("-600.00") and r.es_deficit
    assert r.ingresos_mensual == [Decimal("150.00")] * 12
    assert sum(r.resultado_mensual()) == r.resultado
    cap = {t.capitulo.codigo: t for t in r.capitulos}
    assert cap["I.1"].total == Decimal("1200.00") and cap["I.1"].num_lineas == 1
    assert cap["G.1"].total == Decimal("0.00")
    assert all(isinstance(t.total, Decimal) for t in r.capitulos)


def test_gasto_de_campana_se_totaliza_aparte(borrador, ctx_tesorero: Contexto) -> None:
    borrador.ejercicio.hay_proceso_electoral = True
    borrador.ejercicio.save()
    _linea(ctx_tesorero, borrador, "G.7.1", "5000")
    _linea(ctx_tesorero, borrador, "G.2.1", "100")
    r = resumen_version(borrador)
    assert r.gasto_campana == Decimal("5000.00") and r.gastos == Decimal("5100.00")
