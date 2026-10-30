"""Importación de la ejecución real (CSV), su inmutabilidad y la comparativa con semáforo."""

from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.test import Client

from apps.anexos.comparativa import (
    AMBAR,
    ROJO,
    SIN_CONFIGURAR,
    SIN_DATOS,
    VERDE,
    construir_comparativa,
    semaforo,
)
from apps.anexos.configuracion import parametros_actuales
from apps.anexos.ejecucion import (
    anular_importacion,
    importacion_vigente,
    importar_ejecucion,
    leer_csv,
    plantilla_csv,
)
from apps.anexos.models import EjecucionReal, ImportacionEjecucion, ParametrosAnexosCfg
from apps.auditoria.models import RegistroAuditoria
from apps.presupuesto.models import Linea, Tipo
from tests.conftest import CLAVE
from tests.util_flujo import crear_escenario, version_valida

pytestmark = pytest.mark.django_db
CODIGOS = {"A.1", "B.2"}


def D(x: str) -> Decimal:
    return Decimal(x)


@pytest.fixture
def esc(catalogo):
    return crear_escenario()


@pytest.fixture
def v(esc):
    return version_valida(esc, 2080)


def csv(*filas: str, cabecera: str = "codigo;mes;importe") -> bytes:
    return ("\n".join([cabecera, *filas]) + "\n").encode("utf-8")


# --------------------------------------------------------------------- el lector


def test_un_csv_correcto_se_lee_entero() -> None:
    filas, errores = leer_csv(csv("A.1;1;1.234,56", "A.1;2;10", "B.2;1;-5,5"), CODIGOS, 3)
    assert errores == []
    assert [(f.codigo, f.mes, f.importe) for f in filas] == [
        ("A.1", 1, D("1234.56")),
        ("A.1", 2, D("10")),
        ("B.2", 1, D("-5.5")),
    ]


def test_acepta_bom_y_latin1_y_lineas_en_blanco() -> None:
    contenido = "﻿codigo;mes;importe\n\nA.1;1;5,00\n".encode()
    assert leer_csv(contenido, CODIGOS, 1)[1] == []
    latin = "codigo;mes;importe\nA.1;1;5,00\n".encode("latin-1")
    assert leer_csv(latin, CODIGOS, 1)[1] == []


@pytest.mark.parametrize(
    ("contenido", "esperado"),
    [
        (b"", "vac"),
        (csv(cabecera="a;b;c"), "cabecera"),
        (csv(), "ninguna fila"),
        (csv("A.1;1"), "3 columnas"),
        (csv("Z.9;1;5,00"), "no existe"),
        (csv("A.1;trece;5,00"), "no es un número"),
        (csv("A.1;13;5,00"), "entre 1 y 12"),
        (csv("A.1;5;5,00"), "posterior al mes de corte"),
        (csv("A.1;1;12.50"), "importe"),
        (csv("A.1;1;abc"), "importe"),
        (csv("A.1;1;5,00", "A.1;1;6,00"), "ya aparece"),
    ],
)
def test_los_errores_se_describen_fila_a_fila(contenido: bytes, esperado: str) -> None:
    filas, errores = leer_csv(contenido, CODIGOS, 3)
    assert errores and any(esperado in e for e in errores), errores


def test_el_punto_decimal_es_ambiguo_y_se_rechaza_pero_el_de_millares_no() -> None:
    assert leer_csv(csv("A.1;1;12.50"), CODIGOS, 1)[1]
    assert leer_csv(csv("A.1;1;1.250,00"), CODIGOS, 1)[1] == []


def test_un_fichero_enorme_se_rechaza() -> None:
    assert "pesa más" in leer_csv(b"x" * 2_100_000, CODIGOS, 1)[1][0]


# ---------------------------------------------------------------- la importación


def _codigo(v, partida: str) -> str:
    return Linea.objects.get(version=v, partida__codigo=partida).codigo


def test_importar_guarda_las_filas_la_huella_y_la_auditoria(esc, v) -> None:
    cod = _codigo(v, "G.2.1")
    contenido = csv(f"{cod};1;400,00", f"{cod};2;410,00")
    imp = importar_ejecucion(
        esc.tesorero(), v.ejercicio, nombre_fichero="datos.csv", contenido=contenido, mes_corte=2
    )
    assert imp.filas == 2 and len(imp.huella_fichero) == 64 and imp.estado == "ACTIVA"
    assert EjecucionReal.objects.filter(importacion=imp).count() == 2
    r = RegistroAuditoria.objects.filter(accion="ejecucion.importar").latest("id")
    assert dict(r.despues or {})["huella"] == imp.huella_fichero


def test_si_alguna_fila_falla_no_se_guarda_nada(esc, v) -> None:
    cod = _codigo(v, "G.2.1")
    contenido = csv(f"{cod};1;400,00", "NOEXISTE;1;1,00", f"{cod};2;mal")
    with pytest.raises(ValidationError) as e:
        importar_ejecucion(
            esc.tesorero(), v.ejercicio, nombre_fichero="x.csv", contenido=contenido, mes_corte=2
        )
    assert any("no existe" in m for m in e.value.messages)
    assert any("importe" in m for m in e.value.messages)
    assert ImportacionEjecucion.objects.count() == 0 and EjecucionReal.objects.count() == 0


def test_los_errores_mostrados_tienen_tope(esc, v) -> None:
    filas = [f"Z{n};1;1,00" for n in range(100)]
    with pytest.raises(ValidationError) as e:
        importar_ejecucion(
            esc.tesorero(), v.ejercicio, nombre_fichero="x.csv", contenido=csv(*filas), mes_corte=1
        )
    assert any("errores más" in m for m in e.value.messages)


def test_solo_el_tesorero_importa_y_el_mes_de_corte_se_valida(esc, v) -> None:
    cod = _codigo(v, "G.2.1")
    with pytest.raises(PermissionDenied):
        importar_ejecucion(
            esc.vocal(0),
            v.ejercicio,
            nombre_fichero="x.csv",
            contenido=csv(f"{cod};1;1,00"),
            mes_corte=1,
        )
    with pytest.raises(ValidationError, match="mes de corte"):
        importar_ejecucion(
            esc.tesorero(),
            v.ejercicio,
            nombre_fichero="x.csv",
            contenido=csv(f"{cod};1;1,00"),
            mes_corte=13,
        )


def test_la_comparativa_usa_la_ultima_importacion_activa_y_anular_vuelve_a_la_anterior(
    esc, v
) -> None:
    cod = _codigo(v, "G.2.1")
    a = importar_ejecucion(
        esc.tesorero(),
        v.ejercicio,
        nombre_fichero="a.csv",
        contenido=csv(f"{cod};1;1,00"),
        mes_corte=1,
    )
    b = importar_ejecucion(
        esc.tesorero(),
        v.ejercicio,
        nombre_fichero="b.csv",
        contenido=csv(f"{cod};1;2,00"),
        mes_corte=1,
    )
    assert importacion_vigente(v.ejercicio) == b
    with pytest.raises(ValidationError, match="motivo"):
        anular_importacion(esc.tesorero(), b, "  ")
    anular_importacion(esc.tesorero(), b, "Fichero equivocado")
    assert importacion_vigente(v.ejercicio) == a
    with pytest.raises(ValidationError, match="ya está anulada"):
        anular_importacion(esc.tesorero(), b, "otra vez")
    with pytest.raises(PermissionDenied):
        anular_importacion(esc.vocal(0), a, "no puedo")
    r = RegistroAuditoria.objects.filter(accion="ejecucion.anular").latest("id")
    assert r.motivo == "Fichero equivocado"


def test_la_plantilla_trae_una_fila_por_linea(esc, v) -> None:
    texto = plantilla_csv(v.ejercicio)
    filas = texto.strip().splitlines()
    assert filas[0] == "codigo;mes;importe"
    assert len(filas) == 1 + Linea.objects.filter(version=v).count()
    assert leer_csv(texto.encode(), {f.split(";")[0] for f in filas[1:]}, 1)[1] == []


# ------------------------------------------------------------ inmutabilidad en SQL


@pytest.fixture
def importada(esc, v):
    cod = _codigo(v, "G.2.1")
    return importar_ejecucion(
        esc.tesorero(),
        v.ejercicio,
        nombre_fichero="a.csv",
        contenido=csv(f"{cod};1;1,00"),
        mes_corte=1,
    )


@pytest.mark.parametrize(
    ("sql", "mensaje"),
    [
        ("UPDATE anexos_ejecucionreal SET importe = 99 WHERE importacion_id = %s", "inalterables"),
        ("DELETE FROM anexos_ejecucionreal WHERE importacion_id = %s", "inalterables"),
        ("UPDATE anexos_importacionejecucion SET filas = 7 WHERE id = %s", "solo puede anularse"),
        ("UPDATE anexos_importacionejecucion SET huella_fichero = 'x' WHERE id = %s", "solo puede"),
        (
            "UPDATE anexos_importacionejecucion SET estado = 'ANULADA' WHERE id = %s",
            "solo puede anularse",  # sin motivo
        ),
        ("DELETE FROM anexos_importacionejecucion WHERE id = %s", "no se pueden borrar"),
    ],
)
def test_la_ejecucion_importada_no_se_toca_ni_con_sql(importada, sql, mensaje) -> None:
    with pytest.raises(DatabaseError, match=mensaje), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(sql, (importada.pk,))


def test_anular_con_motivo_por_sql_si_funciona_pero_deshacerlo_no(importada) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE anexos_importacionejecucion SET estado = 'ANULADA', "
            "motivo_anulacion = 'motivo' WHERE id = %s",
            (importada.pk,),
        )
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE anexos_importacionejecucion SET estado = 'ACTIVA' WHERE id = %s",
                (importada.pk,),
            )


# --------------------------------------------------------------------- semáforo


def params(**cambios):
    base = dict(
        semaforo_ambar_pct=D("10"), semaforo_rojo_pct=D("25"), semaforo_importe_minimo=D("50")
    )
    base.update(cambios)
    return parametros_actuales(True).__class__(secciones=(), **base)  # solo importan los umbrales


@pytest.mark.parametrize(
    ("tipo", "presup", "real", "color"),
    [
        (Tipo.GASTO, "1000", "1000", VERDE),
        (Tipo.GASTO, "1000", "900", VERDE),  # gastar menos no es adverso
        (Tipo.GASTO, "1000", "1090", VERDE),  # 9 % < ámbar
        (Tipo.GASTO, "1000", "1100", AMBAR),  # 10 % justo
        (Tipo.GASTO, "1000", "1250", ROJO),  # 25 % justo
        (Tipo.INGRESO, "1000", "1500", VERDE),  # ingresar más no es adverso
        (Tipo.INGRESO, "1000", "850", AMBAR),  # 15 % por debajo
        (Tipo.INGRESO, "1000", "700", ROJO),
        (Tipo.GASTO, "100", "140", VERDE),  # 40 % pero solo 40 € < mínimo de 50 €
        (Tipo.GASTO, "0", "60", ROJO),  # sin base y con desviación
        (Tipo.GASTO, "0", "10", VERDE),  # sin base pero bajo el mínimo
    ],
)
def test_el_semaforo_mira_la_desviacion_adversa(tipo, presup, real, color) -> None:
    assert semaforo(tipo, D(presup), D(real), params())[0] == color


def test_sin_dato_o_sin_umbrales_no_hay_color() -> None:
    assert semaforo(Tipo.GASTO, D("10"), None, params())[0] == SIN_DATOS
    sin = params(semaforo_ambar_pct=None, semaforo_rojo_pct=None)
    color, adversa, pct = semaforo(Tipo.GASTO, D("100"), D("130"), sin)
    assert color == SIN_CONFIGURAR and adversa == D("30") and pct == D("30.0")


# ------------------------------------------------------------------ comparativa


def test_la_comparativa_une_presupuesto_real_y_ejercicio_anterior(esc, v) -> None:
    alquiler = Linea.objects.get(version=v, partida__codigo="G.2.1")  # 4.800 → 400 al mes
    cuotas = Linea.objects.get(version=v, partida__codigo="I.1.1")  # 6.000 → 500 al mes
    Linea.objects.filter(pk=alquiler.pk).update(importe_ejercicio_anterior=D("4000"))
    contenido = csv(
        *[f"{alquiler.codigo};{m};480,00" for m in (1, 2, 3)],  # 20 % más de lo presupuestado
        *[f"{cuotas.codigo};{m};500,00" for m in (1, 2, 3)],  # exacto
    )
    importar_ejecucion(
        esc.tesorero(), v.ejercicio, nombre_fichero="x.csv", contenido=contenido, mes_corte=3
    )
    comp = construir_comparativa(v)
    assert comp.mes_corte == 3 and comp.importacion is not None
    fila = {ln.codigo: ln for ln in comp.lineas}
    a, c = fila[alquiler.codigo], fila[cuotas.codigo]
    assert (a.presupuestado_corte, a.real, a.color) == (D("1200.00"), D("1440.00"), AMBAR)
    assert a.desviacion == D("240.00") and str(a.desviacion_pct) == "20.0"
    assert a.variacion == D("800.00") and str(a.variacion_pct) == "20.0"
    assert (c.real, c.color) == (D("1500.00"), VERDE)
    # una línea sin datos en el fichero no se da por cero
    otra = next(ln for ln in comp.lineas if ln.codigo not in (a.codigo, c.codigo))
    assert otra.real is None and otra.color == SIN_DATOS
    cap = {c.codigo: c for c in comp.capitulos}["I.1"]
    assert cap.real == D("1500.00") and cap.presupuestado_corte == D("1500.00")
    assert cap.anterior is None  # la línea no tiene importe anterior


def test_sin_importacion_no_hay_datos_reales(esc, v) -> None:
    comp = construir_comparativa(v)
    assert comp.importacion is None and comp.mes_corte is None
    assert all(ln.real is None and ln.color == SIN_DATOS for ln in comp.lineas)


def test_el_resumen_de_colores_cuenta_las_lineas(esc, v) -> None:
    alquiler = Linea.objects.get(version=v, partida__codigo="G.2.1")
    importar_ejecucion(
        esc.tesorero(),
        v.ejercicio,
        nombre_fichero="x.csv",
        contenido=csv(f"{alquiler.codigo};1;400,00"),
        mes_corte=1,
    )
    resumen = construir_comparativa(v).resumen_color()
    assert resumen[VERDE] == 1 and resumen[SIN_DATOS] == Linea.objects.filter(version=v).count() - 1


# ------------------------------------------------------------------------ vistas


def cliente(usuario, rol: str) -> Client:
    c = Client()
    assert c.login(username=usuario.username, password=CLAVE)
    c.post("/rol/", {"rol": rol})
    return c


def test_la_pantalla_de_ejecucion_importa_descarga_y_anula(esc, v) -> None:
    c = cliente(esc.t, "TESORERO")
    url = f"/presupuestos/ejercicio/{v.ejercicio.pk}/ejecucion/"
    p = c.get(url).content.decode()
    assert "no sustituye a la contabilidad" in p and "Todavía no hay importaciones" in p
    plantilla = c.get(url + "plantilla.csv")
    assert (
        plantilla["Content-Type"].startswith("text/csv")
        and b"codigo;mes;importe" in plantilla.content
    )
    cod = _codigo(v, "G.2.1")
    malo = SimpleUploadedFile("malo.csv", csv("Z;1;1,00"))
    r = c.post(url, {"fichero": malo, "mes_corte": 1})
    assert "No se ha importado nada" in r.content.decode()
    bueno = SimpleUploadedFile("bueno.csv", csv(f"{cod};1;400,00"))
    assert c.post(url, {"fichero": bueno, "mes_corte": 1}).status_code == 302
    imp = ImportacionEjecucion.objects.get()
    assert "bueno.csv" in c.get(url).content.decode()
    r = c.post(url + f"{imp.pk}/anular/", {"motivo": ""})
    assert r.status_code == 302 and ImportacionEjecucion.objects.get().estado == "ACTIVA"
    c.post(url + f"{imp.pk}/anular/", {"motivo": "Prueba"})
    assert ImportacionEjecucion.objects.get().estado == "ANULADA"


def test_solo_el_tesorero_ve_la_pantalla_de_ejecucion(esc, v) -> None:
    url = f"/presupuestos/ejercicio/{v.ejercicio.pk}/ejecucion/"
    assert cliente(esc.cp[0], "COMISION_PERMANENTE").get(url).status_code == 403
    assert cliente(esc.junta, "JUNTA_GENERAL").get(url + "plantilla.csv").status_code == 403
    assert Client().get(url).status_code == 302


def test_la_pantalla_de_comparativa(esc, v) -> None:
    c = cliente(esc.t, "TESORERO")
    p = c.get(f"/presupuestos/version/{v.pk}/comparativa/").content.decode()
    assert "Todavía no hay ejecución real" in p and "ejercicio anterior" in p
    alquiler = Linea.objects.get(version=v, partida__codigo="G.2.1")
    importar_ejecucion(
        esc.tesorero(),
        v.ejercicio,
        nombre_fichero="x.csv",
        contenido=csv(f"{alquiler.codigo};1;600,00"),
        mes_corte=1,
    )
    p = c.get(f"/presupuestos/version/{v.pk}/comparativa/").content.decode()
    assert "x.csv" in p and "Rojo" in p and "Sin datos" in p
    ParametrosAnexosCfg.objects.filter(es_demo=True).update(semaforo_ambar_pct=None)
    assert (
        "no está configurado"
        in c.get(f"/presupuestos/version/{v.pk}/comparativa/").content.decode()
    )


def test_la_comparativa_respeta_la_visibilidad_por_rol(esc, v) -> None:
    url = f"/presupuestos/version/{v.pk}/comparativa/"
    assert cliente(esc.cp[0], "COMISION_PERMANENTE").get(url).status_code == 404  # borrador
    assert cliente(esc.junta, "JUNTA_GENERAL").get(url).status_code == 404


def test_el_panel_guarda_los_umbrales_del_semaforo_y_los_valida(esc) -> None:
    c = cliente(esc.t, "TESORERO")
    base = {"variaciones_destacadas": "5", "marcas_pendiente": "[COMPLETAR"}
    ok = {
        **base,
        "semaforo_ambar_pct": "8",
        "semaforo_rojo_pct": "20",
        "semaforo_importe_minimo": "25,50",
    }
    assert c.post("/anexos/", ok).status_code == 302
    p = ParametrosAnexosCfg.objects.get(es_demo=True)
    assert (p.semaforo_ambar_pct, p.semaforo_rojo_pct) == (D("8"), D("20"))
    assert p.semaforo_importe_minimo == D("25.50")
    r = c.post("/anexos/", {**base, "semaforo_ambar_pct": "30", "semaforo_rojo_pct": "20"})
    assert "rojo no puede ser menor" in r.content.decode()
    r = c.post("/anexos/", {**base, "semaforo_ambar_pct": "30"})
    assert "ámbar y el rojo" in r.content.decode()
    c.post("/anexos/", {**base, "porcentaje_aviso_limite_campana": "85"})
    assert ParametrosAnexosCfg.objects.get(es_demo=True).porcentaje_aviso_limite_campana == D("85")
