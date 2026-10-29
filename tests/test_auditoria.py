import pytest
from django.db import DatabaseError, connection, transaction

from apps.auditoria.models import AuditoriaInalterable, RegistroAuditoria
from apps.auditoria.servicios import Contexto, registrar


@pytest.fixture
def registro(db: None) -> RegistroAuditoria:
    return registrar(Contexto(None, "", "127.0.0.1"), accion="prueba", entidad="Prueba")


def test_se_puede_registrar(registro: RegistroAuditoria) -> None:
    assert RegistroAuditoria.objects.count() == 1


def test_modelo_no_permite_modificar(registro: RegistroAuditoria) -> None:
    registro.accion = "otra"
    with pytest.raises(AuditoriaInalterable):
        registro.save()


def test_modelo_no_permite_borrar(registro: RegistroAuditoria) -> None:
    with pytest.raises(AuditoriaInalterable):
        registro.delete()
    with pytest.raises(AuditoriaInalterable):
        RegistroAuditoria.objects.all().delete()
    with pytest.raises(AuditoriaInalterable):
        RegistroAuditoria.objects.all().update(accion="x")


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE auditoria_registroauditoria SET accion = 'manipulada'",
        "DELETE FROM auditoria_registroauditoria",
        "TRUNCATE auditoria_registroauditoria",
    ],
)
def test_base_de_datos_rechaza_sql_directo(registro: RegistroAuditoria, sql: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # sin eventos pendientes de la prueba
    with pytest.raises(DatabaseError, match="inalterable"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(sql)
    assert RegistroAuditoria.objects.count() == 1


def test_fila_real_no_se_borra_ni_con_modo_demo(registro: RegistroAuditoria) -> None:
    with pytest.raises(DatabaseError, match="inalterable"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('presupuesto.modo_demo', 'on', true)")
            cursor.execute("DELETE FROM auditoria_registroauditoria")


def test_fila_demo_solo_se_borra_con_modo_demo(db: None) -> None:
    registrar(Contexto(None), accion="demo", entidad="Prueba", es_demo=True)
    with pytest.raises(DatabaseError, match="inalterable"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM auditoria_registroauditoria")
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('presupuesto.modo_demo', 'on', true)")
        cursor.execute("DELETE FROM auditoria_registroauditoria WHERE es_demo")
    assert RegistroAuditoria.objects.count() == 0
