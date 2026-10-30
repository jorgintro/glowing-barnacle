"""La base de datos hace cumplir el flujo y la inmutabilidad (CLAUDE.md §10).

Se prueba con SQL directo y con consultas masivas, saltándose la aplicación: es justo lo que
intentaría alguien que quisiera manipular los datos.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction

from apps.flujo import servicios as fs
from apps.flujo.models import TransicionEstado, Votacion, VotoNominal
from apps.flujo.sello import calcular_hash, verificar_integridad
from apps.presupuesto import donantes as dn
from apps.presupuesto.models import Donacion, Hipotesis, ImporteMensual, Linea, VersionPresupuesto
from tests.util_flujo import (
    A,
    aprobar_cp,
    crear_escenario,
    proponer,
    ratificar,
    version_valida,
    votar_y_cerrar,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def esc(catalogo):
    return crear_escenario()


def sql_falla(sql: str, match: str, params: tuple = ()) -> None:
    with pytest.raises(DatabaseError, match=match), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(sql, params)


def sin_disparador(tabla: str, disparador: str) -> None:
    """Desactiva un disparador SOLO dentro de esta prueba (se deshace al terminar)."""
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute(f"ALTER TABLE {tabla} DISABLE TRIGGER {disparador}")


@pytest.fixture
def propuesta(esc):
    v = version_valida(esc)
    votacion = proponer(esc, v)
    return v, votacion


# ------------------------------------------- el contenido de una versión sellada


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE presupuesto_linea SET importe_anual = 1 WHERE version_id = %s",
        "UPDATE presupuesto_linea SET denominacion = 'cambiada' WHERE version_id = %s",
        "UPDATE presupuesto_importemensual SET importe = 1 WHERE linea_id IN "
        "(SELECT id FROM presupuesto_linea WHERE version_id = %s)",
        "UPDATE presupuesto_hipotesis SET texto = 'otra' WHERE linea_id IN "
        "(SELECT id FROM presupuesto_linea WHERE version_id = %s)",
        "UPDATE presupuesto_donacion SET importe = 1 WHERE version_id = %s",
        "DELETE FROM presupuesto_donacion WHERE version_id = %s",
        "DELETE FROM presupuesto_hipotesis WHERE linea_id IN "
        "(SELECT id FROM presupuesto_linea WHERE version_id = %s)",
        "DELETE FROM presupuesto_importemensual WHERE linea_id IN "
        "(SELECT id FROM presupuesto_linea WHERE version_id = %s)",
    ],
)
def test_el_contenido_de_una_version_propuesta_no_se_toca_ni_con_sql(propuesta, sql) -> None:
    v, _ = propuesta
    sql_falla(sql, "solo lectura", (v.pk,))


def test_no_se_pueden_anadir_lineas_a_una_version_sellada(propuesta) -> None:
    v, _ = propuesta
    otra = Linea.objects.filter(version=v).first()
    assert otra is not None
    with pytest.raises(DatabaseError, match="solo lectura"), transaction.atomic():
        Linea.objects.bulk_create(  # bulk_create se salta las protecciones de la aplicación
            [
                Linea(
                    version=v,
                    partida=otra.partida,
                    codigo="X.9.9.99",
                    denominacion="colada",
                    importe_anual=1,
                )
            ]
        )
    with pytest.raises(DatabaseError, match="solo lectura"), transaction.atomic():
        ImporteMensual.objects.bulk_create([ImporteMensual(linea=otra, mes=1, importe=1)])


def test_el_contenido_de_la_version_tampoco_cambia(propuesta) -> None:
    v, _ = propuesta
    for campo, valor in [
        ("explicacion_resultado", "otra explicación"),
        ("plan_financiacion", "plan nuevo"),
        ("endeudamiento_previsto", 99),
        ("motivo", "otro motivo"),
        ("numero", 9),
    ]:
        with pytest.raises(DatabaseError, match="solo lectura"), transaction.atomic():
            VersionPresupuesto.objects.filter(pk=v.pk).update(**{campo: valor})


def test_la_huella_y_el_proponente_de_una_version_sellada_no_se_cambian(propuesta, esc) -> None:
    v, _ = propuesta
    with pytest.raises(DatabaseError, match="huella"), transaction.atomic():
        VersionPresupuesto.objects.filter(pk=v.pk).update(hash="0" * 64)
    with pytest.raises(DatabaseError, match="proponente"), transaction.atomic():
        VersionPresupuesto.objects.filter(pk=v.pk).update(proponente=esc.cp[0])


def test_requiere_junta_solo_se_decide_al_aprobar_la_cp(propuesta, esc) -> None:
    v, votacion = propuesta
    with pytest.raises(DatabaseError, match="Junta"), transaction.atomic():
        VersionPresupuesto.objects.filter(pk=v.pk).update(requiere_junta=False)
    votar_y_cerrar(esc, votacion, {0: A, 1: A, 2: A})
    with pytest.raises(DatabaseError, match="Junta"), transaction.atomic():
        VersionPresupuesto.objects.filter(pk=v.pk).update(requiere_junta=False)


def test_las_versiones_no_se_borran(propuesta) -> None:
    v, _ = propuesta
    sql_falla(
        "DELETE FROM presupuesto_versionpresupuesto WHERE id = %s", "no se pueden borrar", (v.pk,)
    )


def test_ni_siquiera_el_modo_demo_borra_datos_reales(esc) -> None:
    """El modo demo solo vale para filas marcadas como demostración, nunca para las reales."""
    from apps.presupuesto import servicios as ps
    from tests.conftest import poner_estado
    from tests.util_validaciones import presupuesto_valido

    _, real = ps.crear_ejercicio(esc.tesorero(), anio=2070)  # es_demo = False
    presupuesto_valido(esc.tesorero(), real)
    poner_estado(real, "PROPUESTO")
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('presupuesto.modo_demo', 'on', true)")
    sql_falla("DELETE FROM presupuesto_donacion WHERE version_id = %s", "solo lectura", (real.pk,))
    sql_falla(
        "DELETE FROM presupuesto_versionpresupuesto WHERE id = %s",
        "no se pueden borrar",
        (real.pk,),
    )


# --------------------------------------------------------- transiciones de estado


@pytest.mark.parametrize(
    ("desde", "hacia"),
    [
        ("BORRADOR", "APROBADO_CP"),
        ("BORRADOR", "RATIFICADO_JG"),
        ("BORRADOR", "RECHAZADO"),
        ("BORRADOR", "MODIFICADO"),
        ("PROPUESTO", "RATIFICADO_JG"),
        ("PROPUESTO", "MODIFICADO"),
        ("APROBADO_CP", "BORRADOR"),
        ("APROBADO_CP", "PROPUESTO"),
        ("RATIFICADO_JG", "BORRADOR"),
        ("RATIFICADO_JG", "RECHAZADO"),
        ("RECHAZADO", "BORRADOR"),
        ("RECHAZADO", "PROPUESTO"),
        ("MODIFICADO", "RATIFICADO_JG"),
    ],
)
def test_no_hay_saltos_ni_vuelta_atras_de_estado(esc, desde, hacia) -> None:
    from tests.conftest import poner_estado

    v = version_valida(esc)
    if desde == "MODIFICADO":
        VersionPresupuesto.objects.filter(pk=v.pk).update(tipo_origen="MODIFICACION")
    poner_estado(v, desde)
    with pytest.raises(DatabaseError, match="no permitida"), transaction.atomic():
        VersionPresupuesto.objects.filter(pk=v.pk).update(estado=hacia)
    v.refresh_from_db()
    assert v.estado == desde


def test_modificado_solo_para_versiones_de_modificacion(esc) -> None:
    from tests.conftest import poner_estado

    v = version_valida(esc)
    poner_estado(v, "APROBADO_CP")
    with pytest.raises(DatabaseError, match="no permitida"), transaction.atomic():
        VersionPresupuesto.objects.filter(pk=v.pk).update(estado="MODIFICADO")  # no es modificación


def test_una_version_nueva_solo_nace_en_borrador(esc) -> None:
    v = version_valida(esc)
    with pytest.raises(DatabaseError, match="BORRADOR"), transaction.atomic():
        VersionPresupuesto.objects.create(
            ejercicio=v.ejercicio, numero=9, estado="PROPUESTO", es_demo=True
        )


# ------------------------------------------------------- registros del flujo


def test_las_transiciones_son_inalterables(propuesta) -> None:
    sql_falla("UPDATE flujo_transicionestado SET motivo = 'otro'", "inalterables")
    sql_falla("DELETE FROM flujo_transicionestado", "inalterables")
    assert TransicionEstado.objects.count() == 1


def test_una_votacion_cerrada_y_sus_votos_son_inalterables(esc, propuesta) -> None:
    v, votacion = propuesta
    votar_y_cerrar(esc, votacion, {0: A, 1: A, 2: A})
    sql_falla("UPDATE flujo_votacion SET a_favor = 99", "cerrada es inalterable")
    sql_falla("DELETE FROM flujo_votacion", "cerrada es inalterable")
    sql_falla("UPDATE flujo_votonominal SET voto = 'EN_CONTRA'", "cerrada")
    sql_falla("DELETE FROM flujo_votonominal", "no se pueden borrar")
    with pytest.raises(DatabaseError, match="cerrada"), transaction.atomic():
        VotoNominal.objects.bulk_create(
            [VotoNominal(votacion=votacion, usuario=esc.cp[2], voto="A_FAVOR")]
        )
    assert VotoNominal.objects.filter(votacion=votacion).count() == 3


def test_una_votacion_abierta_si_admite_votos_pero_no_se_borra(esc, propuesta) -> None:
    _, votacion = propuesta
    fs.votar(esc.vocal(0), votacion, A)  # camino normal
    sql_falla("DELETE FROM flujo_votacion", "inalterable")
    sql_falla("DELETE FROM flujo_votonominal", "no se pueden borrar")


# --------------------------------------------------------------- integridad


def test_una_cadena_correcta_pasa_la_verificacion(esc) -> None:
    v = version_valida(esc)
    aprobar_cp(esc, v)
    ratificar(esc, v)
    assert verificar_integridad(v).ok and v.hash == calcular_hash(v)
    call_command("verificar_integridad")  # no lanza


def test_si_alguien_altera_el_contenido_la_huella_lo_delata(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    sin_disparador("presupuesto_linea", "flujo_contenido_linea")
    Linea.objects.filter(version=v, partida__codigo="G.2.1").update(importe_anual=1)
    res = verificar_integridad(v)
    assert not res.ok and "NO coincide con su huella" in res.problemas[0]
    with pytest.raises(CommandError, match="integridad"):
        call_command("verificar_integridad")


def test_una_version_alterada_no_puede_seguir_en_el_flujo(esc) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    sin_disparador("presupuesto_hipotesis", "flujo_contenido_hipotesis")
    Hipotesis.objects.filter(linea__version=v).update(texto="reescrita a escondidas")
    for i in range(3):
        fs.votar(esc.vocal(i), votacion, A)
    with pytest.raises(fs.IntegridadRota):
        fs.cerrar_votacion(esc.vocal(0), votacion)
    with pytest.raises(fs.IntegridadRota):
        fs.devolver(esc.vocal(0), v, "motivo")
    v.refresh_from_db()
    assert v.estado == "PROPUESTO"


def test_la_ratificacion_tambien_comprueba_la_integridad(esc) -> None:
    v = version_valida(esc)
    aprobar_cp(esc, v)
    sin_disparador("presupuesto_donacion", "flujo_contenido_donacion")
    Donacion.objects.filter(version=v).update(importe=1)
    with pytest.raises(fs.IntegridadRota):
        ratificar(esc, v)
    v.refresh_from_db()
    assert v.estado == "APROBADO_CP"


def test_si_alguien_altera_la_hoja_de_control_la_cadena_lo_delata(esc) -> None:
    v = version_valida(esc)
    aprobar_cp(esc, v)
    sin_disparador("flujo_transicionestado", "flujo_inalterable_transicion")
    TransicionEstado.objects.filter(version=v, a_estado="PROPUESTO").update(motivo="reescrito")
    res = verificar_integridad(v)
    assert not res.ok and any("cadena" in p for p in res.problemas)


def test_quitar_una_transicion_de_en_medio_rompe_la_cadena(esc) -> None:
    v = version_valida(esc)
    aprobar_cp(esc, v)
    sin_disparador("flujo_transicionestado", "flujo_inalterable_transicion")
    TransicionEstado.objects.filter(version=v, a_estado="PROPUESTO").delete()
    assert not verificar_integridad(v).ok


def test_la_huella_no_depende_del_orden_de_insercion_ni_cambia_sin_motivo(esc) -> None:
    v = version_valida(esc)
    primero = calcular_hash(v)
    assert calcular_hash(v) == primero  # determinista
    Linea.objects.filter(version=v, partida__codigo="G.2.1").update(denominacion="Otra cosa")
    assert calcular_hash(v) != primero  # cualquier cambio de contenido cambia la huella


def test_la_huella_cubre_las_donaciones(esc) -> None:
    v = version_valida(esc)
    antes = calcular_hash(v)
    d = Donacion.objects.filter(version=v).first()
    assert d is not None
    Donacion.objects.filter(pk=d.pk).update(importe=d.importe + 1)
    assert calcular_hash(v) != antes
    assert dn.CAPITULOS_CON_DONANTES  # (las donaciones son parte del contenido sellado)


def test_votacion_y_voto_siguen_el_ciclo_de_vida(esc, propuesta) -> None:
    _, votacion = propuesta
    assert Votacion.objects.filter(estado="ABIERTA").count() == 1
