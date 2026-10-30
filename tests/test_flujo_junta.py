"""Convocatoria y ratificación de la Junta General (CLAUDE.md §4, §5 y reglas O-002, O-004)."""

from datetime import timedelta
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.servicios import Contexto
from apps.flujo import servicios as fs
from apps.flujo.models import Convocatoria, Ratificacion, TransicionEstado
from apps.flujo.sello import verificar_integridad
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import Linea, TipoOrigen
from apps.usuarios.roles import Rol
from tests.conftest import crear
from tests.util_flujo import (
    aprobar_cp,
    crear_escenario,
    organicas_estrictas,
    proponer,
    ratificar,
    version_valida,
)

pytestmark = pytest.mark.django_db
HOY = timezone.localdate()


@pytest.fixture
def esc(catalogo):
    return crear_escenario()


@pytest.fixture
def aprobada(esc):
    v = version_valida(esc)
    aprobar_cp(esc, v)
    return v


# ----------------------------------------------------------------------- convocatoria


def test_el_tesorero_o_la_junta_registran_la_convocatoria(esc, aprobada) -> None:
    c = fs.registrar_convocatoria(
        esc.tesorero(),
        aprobada,
        fecha_convocatoria=HOY - timedelta(days=10),
        fecha_sesion=HOY + timedelta(days=5),
        referencia="Carta nº 4",
    )
    assert c.referencia == "Carta nº 4" and c.registrada_por == esc.t
    fs.registrar_convocatoria(
        esc.la_junta(), aprobada, fecha_convocatoria=HOY, fecha_sesion=HOY + timedelta(days=1)
    )
    assert Convocatoria.objects.filter(version=aprobada).count() == 2
    assert RegistroAuditoria.objects.filter(accion="convocatoria.registrar").count() == 2


def test_convocatoria_con_datos_o_roles_incorrectos(esc, aprobada) -> None:
    with pytest.raises(PermissionDenied):
        fs.registrar_convocatoria(esc.vocal(0), aprobada, fecha_convocatoria=HOY, fecha_sesion=HOY)
    with pytest.raises(ValidationError, match="anterior a la convocatoria"):
        fs.registrar_convocatoria(
            esc.tesorero(), aprobada, fecha_convocatoria=HOY, fecha_sesion=HOY - timedelta(days=1)
        )
    borrador = version_valida(esc, anio=2061)
    with pytest.raises(ValidationError, match="Aprobado"):
        fs.registrar_convocatoria(
            esc.tesorero(), borrador, fecha_convocatoria=HOY, fecha_sesion=HOY
        )


# ----------------------------------------------------------------------- ratificación


def test_la_junta_ratifica_y_la_version_pasa_a_ratificada(esc, aprobada) -> None:
    r = ratificar(esc, aprobada, observaciones="Sin comentarios")
    aprobada.refresh_from_db()
    assert aprobada.estado == EstadoVersion.RATIFICADO_JG and not aprobada.editable
    assert (r.resultado, r.referencia_acta, r.rol) == (
        "RATIFICADO",
        "ACTA-PRUEBA",
        Rol.JUNTA_GENERAL,
    )
    assert r.fecha_sesion == HOY and r.convocatoria is not None and r.registrada_por == esc.junta
    assert fs.vigente(aprobada.ejercicio) == aprobada
    ultima = TransicionEstado.objects.filter(version=aprobada).latest("id")
    assert ultima.a_estado == "RATIFICADO_JG" and "ACTA-PRUEBA" in ultima.motivo
    assert verificar_integridad(aprobada).ok


def test_la_junta_rechaza_y_se_abre_un_nuevo_borrador(esc, aprobada) -> None:
    n_lineas = Linea.objects.filter(version=aprobada).count()
    ratificar(esc, aprobada, resultado="RECHAZADO")
    aprobada.refresh_from_db()
    assert aprobada.estado == EstadoVersion.RECHAZADO
    nuevo = aprobada.ejercicio.versiones.get(numero=2)
    assert nuevo.estado == EstadoVersion.BORRADOR and nuevo.tipo_origen == TipoOrigen.TRAS_RECHAZO
    assert (
        nuevo.version_origen == aprobada and Linea.objects.filter(version=nuevo).count() == n_lineas
    )
    assert fs.vigente(aprobada.ejercicio) is None


def test_el_tesorero_registra_la_ratificacion_solo_si_la_configuracion_lo_permite(
    esc, aprobada, monkeypatch
) -> None:
    datos: dict[str, Any] = {
        "fecha_sesion": HOY,
        "resultado": "RATIFICADO",
        "referencia_acta": "ACTA-1",
    }
    organicas_estrictas(monkeypatch)  # solo la Junta
    with pytest.raises(PermissionDenied):
        fs.registrar_ratificacion(esc.tesorero(), aprobada, avisos_aceptados=["O-004"], **datos)
    with pytest.raises(PermissionDenied):
        fs.registrar_ratificacion(esc.vocal(0), aprobada, avisos_aceptados=["O-004"], **datos)
    assert not Ratificacion.objects.exists()
    monkeypatch.undo()  # configuración demo: el Tesorero también puede
    r = fs.registrar_ratificacion(esc.tesorero(), aprobada, avisos_aceptados=["O-004"], **datos)
    assert r.rol == Rol.TESORERO


@pytest.mark.parametrize(
    ("cambio", "texto"),
    [
        ({"referencia_acta": "  "}, "referencia al acta"),
        ({"fecha_sesion": None}, "fecha de la sesión"),
        ({"fecha_sesion": HOY + timedelta(days=3)}, "futura"),
        ({"fecha_sesion": HOY - timedelta(days=1)}, "antes de la aprobación"),
        ({"resultado": "QUIZAS"}, "RATIFICADO o RECHAZADO"),
    ],
)
def test_o002_ratificacion_incompleta_o_incoherente_bloquea(esc, aprobada, cambio, texto) -> None:
    fs.registrar_convocatoria(
        esc.tesorero(), aprobada, fecha_convocatoria=HOY - timedelta(days=5), fecha_sesion=HOY
    )
    datos: dict[str, Any] = {
        "fecha_sesion": HOY,
        "resultado": "RATIFICADO",
        "referencia_acta": "ACTA-1",
    }
    datos.update(cambio)
    with pytest.raises(ValidationError, match=texto):
        fs.registrar_ratificacion(esc.la_junta(), aprobada, **datos)
    aprobada.refresh_from_db()
    assert aprobada.estado == EstadoVersion.APROBADO_CP and not Ratificacion.objects.exists()


def test_o004_sin_convocatoria_hay_que_aceptar_el_aviso(esc, aprobada) -> None:
    datos: dict[str, Any] = {
        "fecha_sesion": HOY,
        "resultado": "RATIFICADO",
        "referencia_acta": "ACTA-1",
    }
    with pytest.raises(ValidationError, match="convocatoria"):
        fs.registrar_ratificacion(esc.la_junta(), aprobada, **datos)
    fs.registrar_ratificacion(esc.la_junta(), aprobada, avisos_aceptados=["O-004"], **datos)
    aprobada.refresh_from_db()
    assert aprobada.estado == EstadoVersion.RATIFICADO_JG
    assert TransicionEstado.objects.filter(version=aprobada).latest("id").avisos_aceptados == [
        "O-004"
    ]


def test_o004_convocatoria_posterior_a_la_sesion_tambien_avisa(esc, aprobada) -> None:
    fs.registrar_convocatoria(
        esc.tesorero(),
        aprobada,
        fecha_convocatoria=HOY + timedelta(days=2),
        fecha_sesion=HOY + timedelta(days=3),
    )
    datos: dict[str, Any] = {
        "fecha_sesion": HOY,
        "resultado": "RATIFICADO",
        "referencia_acta": "ACTA-1",
    }
    with pytest.raises(ValidationError, match="posterior"):
        fs.registrar_ratificacion(esc.la_junta(), aprobada, **datos)


def test_solo_se_ratifica_lo_aprobado_por_la_cp_y_una_sola_vez(esc, aprobada) -> None:
    datos: dict[str, Any] = {
        "fecha_sesion": HOY,
        "resultado": "RATIFICADO",
        "referencia_acta": "A",
        "avisos_aceptados": ["O-004"],
    }
    borrador = version_valida(esc, anio=2061)
    with pytest.raises(ValidationError, match="Aprobado"):
        fs.registrar_ratificacion(esc.la_junta(), borrador, **datos)
    propuesta = version_valida(esc, anio=2062)
    proponer(esc, propuesta)
    with pytest.raises(ValidationError, match="Aprobado"):
        fs.registrar_ratificacion(esc.la_junta(), propuesta, **datos)
    fs.registrar_ratificacion(esc.la_junta(), aprobada, **datos)
    with pytest.raises(ValidationError, match="Aprobado"):
        fs.registrar_ratificacion(esc.la_junta(), aprobada, **datos)
    assert Ratificacion.objects.count() == 1


def test_una_ratificacion_es_inalterable_en_la_base_de_datos(esc, aprobada) -> None:
    ratificar(esc, aprobada)
    for sql in (
        "UPDATE flujo_ratificacion SET resultado = 'RECHAZADO'",
        "DELETE FROM flujo_ratificacion",
        "UPDATE flujo_convocatoria SET fecha_sesion = '2000-01-01'",
        "DELETE FROM flujo_convocatoria",
    ):
        with pytest.raises(DatabaseError, match="inalterables"), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql)
    assert Ratificacion.objects.count() == 1


def test_el_hash_se_conserva_durante_toda_la_ratificacion(esc, aprobada) -> None:
    sello = aprobada.hash
    ratificar(esc, aprobada)
    aprobada.refresh_from_db()
    assert aprobada.hash == sello
    assert {t.hash_version for t in TransicionEstado.objects.filter(version=aprobada)} == {sello}


def test_los_usuarios_reales_no_pueden_ratificar_versiones_demo_con_la_cuenta_equivocada(
    esc, aprobada
) -> None:
    ajeno = crear("junta_real", Rol.JUNTA_GENERAL)
    r = fs.registrar_ratificacion(
        Contexto(ajeno, Rol.JUNTA_GENERAL),
        aprobada,
        fecha_sesion=HOY,
        resultado="RATIFICADO",
        referencia_acta="X",
        avisos_aceptados=["O-004"],
    )
    # La Junta no se calcula por miembros: basta el rol. Queda constancia de quién fue.
    assert r.registrada_por == ajeno
