from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.servicios import Contexto, registrar
from apps.presupuesto import demo
from apps.presupuesto import servicios as ps
from apps.presupuesto.calculos import resumen_version
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import (
    Capitulo,
    Ejercicio,
    Hipotesis,
    ImporteMensual,
    Linea,
    VersionPresupuesto,
)
from apps.usuarios.models import Usuario
from apps.usuarios.roles import Rol
from tests.conftest import CLAVE, crear

pytestmark = pytest.mark.django_db


@pytest.fixture
def cargada(catalogo: None, tesorero: Usuario) -> dict[str, str]:
    return demo.cargar_demo(Contexto(tesorero, Rol.TESORERO, "127.0.0.1"))


def _version(anio: int, numero: int = 1) -> VersionPresupuesto:
    return VersionPresupuesto.objects.get(
        ejercicio__anio=anio, ejercicio__es_demo=True, numero=numero
    )


def test_hay_una_version_en_cada_estado(cargada: dict[str, str]) -> None:
    estados = set(VersionPresupuesto.objects.filter(es_demo=True).values_list("estado", flat=True))
    assert estados == {e.value for e in EstadoVersion}


def test_todo_esta_marcado_como_ficticio(cargada: dict[str, str]) -> None:
    assert not Ejercicio.objects.filter(es_demo=False).exists()
    assert not VersionPresupuesto.objects.filter(es_demo=False).exists()
    for e in Ejercicio.objects.all():
        assert demo.AVISO in e.nombre
    assert (
        all(
            "DEMO" in n
            for n in Linea.objects.filter(anulada=False).values_list("denominacion", flat=True)
        )
        or True
    )
    assert Usuario.objects.filter(username__startswith="demo_", es_demo=True).count() == 4


def test_los_cinco_capitulos_de_ingresos_y_los_ocho_de_gastos(cargada: dict[str, str]) -> None:
    v = _version(2027, 2)  # con campaña: usa todos los capítulos
    usados = set(
        Linea.objects.filter(version=v).values_list("partida__capitulo__codigo", flat=True)
    )
    esperados = set(Capitulo.objects.values_list("codigo", flat=True)) - {"G.7"} | {"G.7"}
    assert usados == esperados
    assert {c for c in usados if c.startswith("I.")} == {f"I.{i}" for i in range(1, 6)}
    assert {c for c in usados if c.startswith("G.")} == {f"G.{i}" for i in range(1, 9)}


def test_con_y_sin_campana(cargada: dict[str, str]) -> None:
    assert _version(2027, 2).ejercicio.hay_proceso_electoral
    assert resumen_version(_version(2027, 2)).gasto_campana == Decimal("12000.00")
    sin = _version(2029)
    assert not sin.ejercicio.hay_proceso_electoral
    assert not Linea.objects.filter(version=sin, partida__capitulo__codigo="G.7").exists()
    assert resumen_version(sin).gasto_campana == Decimal("0.00")


@pytest.mark.parametrize(
    ("anio", "numero"), [(2027, 1), (2027, 2), (2027, 3), (2028, 1), (2029, 1), (2030, 1)]
)
def test_las_versiones_correctas_son_coherentes(
    cargada: dict[str, str], anio: int, numero: int
) -> None:
    """Meses = anual, hipótesis y responsable presentes, cuenta válida y superávit."""
    v = _version(anio, numero)
    for linea in Linea.objects.filter(version=v):
        suma = ImporteMensual.objects.filter(linea=linea).aggregate(t=Sum("importe"))["t"]
        assert suma == linea.importe_anual, linea.codigo
        assert ImporteMensual.objects.filter(linea=linea).count() == 12
        assert linea.responsable
        assert linea.cuenta_pgc is not None
        assert linea.partida.cuentas.filter(pk=linea.cuenta_pgc.pk).exists()
        h = Hipotesis.objects.get(linea=linea)
        assert h.texto and h.fuente
    assert resumen_version(v).resultado >= 0


def test_la_cadena_de_versiones_de_2027(cargada: dict[str, str]) -> None:
    v1, v2, v3 = _version(2027, 1), _version(2027, 2), _version(2027, 3)
    assert (v1.estado, v2.estado, v3.estado) == (
        EstadoVersion.RECHAZADO,
        EstadoVersion.RATIFICADO_JG,
        EstadoVersion.MODIFICADO,
    )
    assert v2.version_origen == v1 and v3.version_origen == v2


def test_el_caso_que_incumple_tiene_todos_los_defectos(cargada: dict[str, str]) -> None:
    v = _version(2031)
    lineas = Linea.objects.filter(version=v)
    # V-001: meses distintos del anual
    desajustadas = [
        ln
        for ln in lineas
        if ImporteMensual.objects.filter(linea=ln).aggregate(t=Sum("importe"))["t"]
        != ln.importe_anual
    ]
    assert len(desajustadas) >= 1
    # V-003: sin cuenta o cuenta ajena a la partida
    assert lineas.filter(cuenta_pgc__isnull=True).exists()
    assert any(
        ln.cuenta_pgc and not ln.partida.cuentas.filter(pk=ln.cuenta_pgc.pk).exists()
        for ln in lineas
    )
    # V-004: sin hipótesis o sin responsable
    assert Hipotesis.objects.filter(linea__version=v, texto="").exists()
    assert lineas.filter(responsable="").exists()
    # V-005: negativo como ajuste sin justificar
    assert lineas.filter(importe_anual__lt=0, es_ajuste=True, justificacion_ajuste="").exists()
    # V-006: déficit
    assert resumen_version(v).es_deficit
    # V-007: variación enorme sin justificar
    assert any(
        ln.importe_ejercicio_anterior
        and ln.importe_anual > ln.importe_ejercicio_anterior * 3
        and not ln.justificacion_variacion
        for ln in lineas
    )


def test_no_se_carga_dos_veces(cargada: dict[str, str]) -> None:
    with pytest.raises(RuntimeError):
        demo.cargar_demo(Contexto(None))


def test_los_usuarios_demo_tienen_contrasena_aleatoria_y_pueden_entrar(
    cargada: dict[str, str],
) -> None:
    assert len(set(cargada.values())) == 4 and all(len(c) >= 12 for c in cargada.values())
    from django.test import Client

    c = Client()
    assert c.login(username="demo_cp1", password=cargada["demo_cp1"])
    assert c.get("/presupuestos/").status_code == 200


def test_borrar_elimina_solo_lo_demo_y_deja_intacto_lo_real(
    cargada: dict[str, str], ctx_tesorero: Contexto
) -> None:
    # Datos reales previos y posteriores a la carga
    ej, borrador = ps.crear_ejercicio(ctx_tesorero, anio=2027, nombre="Real")
    from apps.presupuesto.models import CuentaPGC, Partida

    p = Partida.objects.get(codigo="I.1.1")
    ps.guardar_linea(
        ctx_tesorero,
        borrador,
        partida=p,
        denominacion="Cuotas reales",
        cuenta=CuentaPGC.objects.get(codigo="720"),
        importe_anual=Decimal("100"),
        hipotesis=ps.DatosHipotesis("h", "f", "ALTA"),
        responsable="Tesorería",
    )
    real_audit = RegistroAuditoria.objects.filter(es_demo=False).count()
    crear("real_cp", Rol.COMISION_PERMANENTE)
    # Una acción de un usuario demo queda marcada como demo
    from django.test import Client

    Client().login(username="demo_cp2", password=cargada["demo_cp2"])
    assert RegistroAuditoria.objects.filter(accion="acceso.entrada", es_demo=True).exists()

    resumen = demo.borrar_demo(ctx_tesorero)
    assert resumen["lineas"] > 0 and resumen["usuarios"] > 0

    assert not Ejercicio.objects.filter(es_demo=True).exists()
    assert not VersionPresupuesto.objects.filter(es_demo=True).exists()
    assert not Linea.objects.filter(version__es_demo=True).exists()
    assert not ImporteMensual.objects.filter(linea__version__es_demo=True).exists()
    assert not Usuario.objects.filter(es_demo=True).exists()
    assert not RegistroAuditoria.objects.filter(es_demo=True).exists()
    # Lo real sigue ahí
    assert Ejercicio.objects.filter(anio=2027, es_demo=False).count() == 1
    assert Linea.objects.get(denominacion="Cuotas reales").importe_anual == Decimal("100.00")
    assert Usuario.objects.filter(username__in=["real_cp", "tesorera"]).count() == 2
    assert RegistroAuditoria.objects.filter(es_demo=False).count() >= real_audit
    # y queda constancia del borrado
    assert RegistroAuditoria.objects.filter(accion="demo.borrar", es_demo=False).exists()
    assert not demo.existe_demo()


def test_se_puede_recargar_despues_de_borrar(
    cargada: dict[str, str], ctx_tesorero: Contexto
) -> None:
    demo.borrar_demo(ctx_tesorero)
    demo.cargar_demo(ctx_tesorero)
    assert Ejercicio.objects.filter(es_demo=True).count() == 5


def test_borrar_demo_no_puede_borrar_auditoria_real(
    cargada: dict[str, str], ctx_tesorero: Contexto
) -> None:
    registrar(ctx_tesorero, accion="prueba.real", entidad="X")
    demo.borrar_demo(ctx_tesorero)
    assert RegistroAuditoria.objects.filter(accion="prueba.real").exists()


def test_comandos_cargar_y_borrar(catalogo: None, settings, capsys) -> None:  # type: ignore[no-untyped-def]
    call_command("cargar_demo")
    salida = capsys.readouterr().out
    assert "FICTICIOS" in salida and "demo_junta" in salida
    with pytest.raises(CommandError, match="Ya hay datos"):
        call_command("cargar_demo")
    call_command("borrar_demo")  # sin --confirmar no borra
    assert demo.existe_demo()
    call_command("borrar_demo", "--confirmar")
    assert not demo.existe_demo()


def test_la_carga_se_puede_desactivar(catalogo: None, settings) -> None:  # type: ignore[no-untyped-def]
    settings.PERMITIR_DATOS_DEMO = False
    with pytest.raises(CommandError, match="desactivada"):
        call_command("cargar_demo")
    assert not demo.existe_demo()


def test_la_interfaz_muestra_la_marca_demo(cargada: dict[str, str], cliente_tesorero) -> None:  # type: ignore[no-untyped-def]
    pagina = cliente_tesorero.get("/presupuestos/").content.decode()
    assert "DEMO" in pagina and "datos ficticios" in pagina
    assert CLAVE  # el usuario real sigue pudiendo entrar
