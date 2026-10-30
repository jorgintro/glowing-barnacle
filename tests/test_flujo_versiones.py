"""Modificaciones presupuestarias y prórroga (CLAUDE.md §5.2 y §5.3)."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.flujo import servicios as fs
from apps.flujo.sello import verificar_integridad
from apps.presupuesto import servicios as ps
from apps.presupuesto.calculos import resumen_version
from apps.presupuesto.configuracion import UmbralModificacion, cargar_configuracion
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import Donacion, Linea, TipoOrigen
from tests.util_flujo import (
    A,
    N,
    aprobar_cp,
    crear_escenario,
    proponer,
    ratificar,
    version_valida,
    vigente,
    votar_y_cerrar,
)
from tests.util_validaciones import linea

pytestmark = pytest.mark.django_db


@pytest.fixture
def esc(catalogo):
    return crear_escenario()


def _cfg_con(**cambios):  # type: ignore[no-untyped-def]
    base = cargar_configuracion(True)
    return replace(base, organicas=replace(base.organicas, **cambios))


def _borrador_de_modificacion(esc, base, importe_extra: str | None = "400"):  # type: ignore[no-untyped-def]
    m = fs.crear_modificacion(esc.tesorero(), base, "Reforma de la sede")
    if importe_extra:
        linea(esc.tesorero(), m, "G.2.5", importe_extra, tipo="EXTRAORDINARIO")
    return m


def _cerrar_cp(esc, m):  # type: ignore[no-untyped-def]
    votacion = proponer(esc, m)
    votar_y_cerrar(esc, votacion, {0: A, 1: A, 2: A, 3: N})
    m.refresh_from_db()


# ------------------------------------------------------------------- modificaciones


def test_la_modificacion_copia_la_version_vigente_y_enlaza_con_ella(esc) -> None:
    base = vigente(esc)
    n = Linea.objects.filter(version=base, anulada=False).count()
    n_don = Donacion.objects.filter(version=base).count()
    m = fs.crear_modificacion(esc.tesorero(), base, "  Hay que ampliar la sede ")
    assert m.estado == EstadoVersion.BORRADOR and m.editable and m.numero == 2
    assert m.tipo_origen == TipoOrigen.MODIFICACION and m.version_origen == base
    assert m.motivo == "Hay que ampliar la sede"
    assert (
        Linea.objects.filter(version=m).count() == n
        and Donacion.objects.filter(version=m).count() == n_don
    )
    assert m.explicacion_resultado == base.explicacion_resultado


def test_la_modificacion_exige_rol_motivo_y_una_version_vigente(esc) -> None:
    base = vigente(esc)
    with pytest.raises(PermissionDenied):
        fs.crear_modificacion(esc.vocal(0), base, "x")
    with pytest.raises(ValidationError, match="justificación"):
        fs.crear_modificacion(esc.tesorero(), base, "  ")
    borrador = version_valida(esc, anio=2061)
    with pytest.raises(ValidationError, match="Ratificado"):
        fs.crear_modificacion(esc.tesorero(), borrador, "x")


def test_no_se_abren_dos_modificaciones_a_la_vez(esc) -> None:
    base = vigente(esc)
    fs.crear_modificacion(esc.tesorero(), base, "primera")
    with pytest.raises(ValidationError, match="en curso"):
        fs.crear_modificacion(esc.tesorero(), base, "segunda")


def test_una_modificacion_pequena_la_cierra_la_cp_sin_pasar_por_la_junta(esc) -> None:
    base = vigente(esc)
    m = _borrador_de_modificacion(esc, base, "400")  # 400 € < umbral ficticio de 500 €
    _cerrar_cp(esc, m)
    assert m.estado == EstadoVersion.MODIFICADO and m.requiere_junta is False
    assert fs.vigente(m.ejercicio) == m  # la modificación aprobada es ya la vigente
    assert verificar_integridad(m).ok
    pasos = [t.a_estado for t in m.transiciones.order_by("id")]
    assert pasos == ["PROPUESTO", "APROBADO_CP", "MODIFICADO"]
    assert "solo por la Comisión Permanente" in m.transiciones.latest("id").motivo
    with pytest.raises(ValidationError):  # y ya no hay nada que ratificar
        ratificar(esc, m)


def test_una_modificacion_grande_vuelve_a_la_junta(esc) -> None:
    base = vigente(esc)
    m = _borrador_de_modificacion(esc, base, "5000")
    from apps.presupuesto import donantes as dn

    dn.guardar_resultado(  # el gasto extra deja un déficit: hace falta plan de financiación (V-006)
        esc.tesorero(),
        m,
        explicacion="Reforma grande.",
        plan_financiacion="Derrama extraordinaria.",
        endeudamiento=Decimal("0"),
    )
    _cerrar_cp(esc, m)
    assert m.estado == EstadoVersion.APROBADO_CP and m.requiere_junta is True
    ratificar(esc, m)
    m.refresh_from_db()
    assert m.estado == EstadoVersion.RATIFICADO_JG and fs.vigente(m.ejercicio) == m


def test_se_puede_modificar_una_modificacion_ya_aprobada(esc) -> None:
    base = vigente(esc)
    m = _borrador_de_modificacion(esc, base, "400")
    _cerrar_cp(esc, m)
    segunda = fs.crear_modificacion(esc.tesorero(), m, "Otra reforma")
    assert segunda.version_origen == m and segunda.numero == 3


def test_una_transferencia_entre_partidas_depende_del_reglamento(esc) -> None:
    base = vigente(esc)
    m = fs.crear_modificacion(esc.tesorero(), base, "Mover dinero de alquiler a mantenimiento")
    alquiler = Linea.objects.get(version=m, partida__codigo="G.2.1")
    assert alquiler.cuenta_pgc is not None
    ps.guardar_linea(  # 4.800 → 4.000
        esc.tesorero(),
        m,
        partida=alquiler.partida,
        denominacion=alquiler.denominacion,
        cuenta=alquiler.cuenta_pgc,
        importe_anual=Decimal("4000"),
        hipotesis=ps.DatosHipotesis("h", "f"),
        responsable="R",
        linea=alquiler,
    )
    linea(esc.tesorero(), m, "G.2.5", "800")  # los 800 € van a otra partida: total igual
    junta, razon = fs.decidir_requiere_junta(m, cargar_configuracion(True))
    assert junta is False and "Transferencia" in razon  # la demo permite solo CP
    junta, razon = fs.decidir_requiere_junta(m, _cfg_con(transferencias_solo_cp=False))
    assert junta is True and "no la deja" in razon


def test_decidir_requiere_junta_con_distintos_umbrales(esc) -> None:
    base = vigente(esc)
    m = _borrador_de_modificacion(esc, base, "400")

    def por_importe(x: str):  # type: ignore[no-untyped-def]
        return _cfg_con(umbral_modificacion_junta=UmbralModificacion("IMPORTE", Decimal(x)))

    def por_porcentaje(x: Decimal):  # type: ignore[no-untyped-def]
        return _cfg_con(umbral_modificacion_junta=UmbralModificacion("PORCENTAJE", x))

    assert fs.decidir_requiere_junta(m, _cfg_con(umbral_modificacion_junta=None))[0] is True
    assert fs.decidir_requiere_junta(m, por_importe("400"))[0] is False  # 400 no supera 400
    assert fs.decidir_requiere_junta(m, por_importe("399.99"))[0] is True
    resumen = resumen_version(base)
    pct = Decimal("400") * 100 / max(resumen.ingresos, resumen.gastos)
    assert fs.decidir_requiere_junta(m, por_porcentaje(pct + 1))[0] is False
    assert fs.decidir_requiere_junta(m, por_porcentaje(pct / 2))[0] is True


def test_una_version_nueva_siempre_va_a_la_junta(esc) -> None:
    v = version_valida(esc)
    assert fs.decidir_requiere_junta(v, cargar_configuracion(True))[0] is True


# ------------------------------------------------------------------------- prórroga


@pytest.fixture
def ejercicio_siguiente(esc):
    base = vigente(esc, anio=2061, campana=True)  # con campaña: para ver qué se excluye
    _, v = ps.crear_ejercicio(esc.tesorero(), anio=2062, es_demo=True)
    return base, v.ejercicio


def test_la_prorroga_solo_se_ofrece_a_partir_del_1_de_enero(esc, ejercicio_siguiente) -> None:
    _, ej = ejercicio_siguiente
    ok, motivo = fs.prorroga_disponible(ej, date(2061, 12, 31))
    assert not ok and "no ha empezado" in motivo
    assert fs.prorroga_disponible(ej, date(2062, 1, 1)) == (True, "")


def test_la_prorroga_copia_solo_lo_recurrente_y_excluye_la_campana(
    esc, ejercicio_siguiente
) -> None:
    base, ej = ejercicio_siguiente
    assert Linea.objects.filter(version=base, partida__codigo="G.7.1").exists()
    p = fs.crear_prorroga(esc.tesorero(), ej, hoy=date(2062, 1, 15))
    assert p.es_prorroga and p.tipo_origen == TipoOrigen.PRORROGA and p.version_origen == base
    assert (
        p.estado == EstadoVersion.BORRADOR and p.numero == 2 and "provisional" in p.motivo.lower()
    )
    copiadas = Linea.objects.filter(version=p)
    assert copiadas.exists()
    assert not copiadas.filter(partida__codigo="G.7.1").exists()  # la campaña no se prorroga
    assert not copiadas.filter(dimension="CAMPANA").exists()
    assert not copiadas.exclude(tipo="RECURRENTE").exists()
    assert copiadas.count() < Linea.objects.filter(version=base).count()
    # las donaciones de las líneas copiadas acompañan, y cada una cuelga de una línea de la prórroga
    donaciones = Donacion.objects.filter(version=p)
    assert donaciones.count() == Donacion.objects.filter(version=base).count() == 4
    assert all(d.linea.version_id == p.pk for d in donaciones)


def test_la_prorroga_se_genera_una_sola_vez_y_exige_ser_tesorero(esc, ejercicio_siguiente) -> None:
    _, ej = ejercicio_siguiente
    with pytest.raises(PermissionDenied):
        fs.crear_prorroga(esc.vocal(0), ej, hoy=date(2062, 2, 1))
    fs.crear_prorroga(esc.tesorero(), ej, hoy=date(2062, 2, 1))
    with pytest.raises(ValidationError, match="Ya se generó"):
        fs.crear_prorroga(esc.tesorero(), ej, hoy=date(2062, 2, 2))


def test_no_hay_prorroga_si_ya_hay_presupuesto_o_nada_que_prorrogar(
    esc, ejercicio_siguiente
) -> None:
    base, ej = ejercicio_siguiente
    sin_anterior = ps.crear_ejercicio(esc.tesorero(), anio=2100, es_demo=True)[0]
    ok, motivo = fs.prorroga_disponible(sin_anterior, date(2100, 5, 1))
    assert not ok and "ejercicio anterior" in motivo
    v = ej.versiones.first()
    assert v is not None
    from apps.presupuesto import donantes as dn
    from tests.util_validaciones import presupuesto_valido

    presupuesto_valido(esc.tesorero(), v)
    aprobar_cp(esc, v)
    ratificar(esc, v)
    ok, motivo = fs.prorroga_disponible(ej, date(2062, 3, 1))
    assert not ok and "ya tiene un presupuesto aprobado" in motivo
    assert dn.CAPITULOS_CON_DONANTES and base


def test_la_prorroga_sigue_el_ciclo_normal_y_queda_marcada_como_provisional(
    esc, ejercicio_siguiente
) -> None:
    _, ej = ejercicio_siguiente
    p = fs.crear_prorroga(esc.tesorero(), ej, hoy=date(2062, 1, 2))
    # puede proponerse y aprobarse igual que cualquier versión
    from apps.presupuesto import donantes as dn

    dn.guardar_resultado(
        esc.tesorero(),
        p,
        explicacion="Prórroga provisional.",
        plan_financiacion="Se mantiene lo anterior.",
        endeudamiento=Decimal("0"),
    )
    aprobar_cp(esc, p)
    assert p.es_prorroga and p.estado == EstadoVersion.APROBADO_CP and p.requiere_junta is True
