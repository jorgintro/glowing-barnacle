"""Memoria explicativa (V-008), su configuración, su sellado y su inmutabilidad."""

from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction

from apps.anexos import servicios as an
from apps.anexos.completitud import estado_secciones, problemas_memoria
from apps.anexos.configuracion import (
    ParametrosAnexos,
    asegurar_configuracion,
    parametros_actuales,
    parametros_de_version,
)
from apps.anexos.memoria import (
    bloque_hipotesis,
    bloque_resumen,
    bloque_riesgos,
    construir_memoria,
    texto_inicial,
)
from apps.anexos.models import ParametrosAnexosCfg, SeccionMemoria, SeccionMemoriaCfg
from apps.auditoria.models import RegistroAuditoria
from apps.flujo import servicios as fs
from apps.flujo.sello import calcular_hash, contenido_canonico, verificar_integridad
from apps.presupuesto import servicios as ps
from apps.validaciones.motor import validar_version
from tests.util_flujo import (
    aprobar_cp,
    crear_escenario,
    proponer,
    ratificar,
    version_valida,
)
from tests.util_validaciones import HOY, cfg_demo, codigos, validar

pytestmark = pytest.mark.django_db


@pytest.fixture
def esc(catalogo):
    return crear_escenario()


def borrador_sin_memoria(esc, anio: int = 2061):
    """Presupuesto valido salvo la memoria, que queda vacía."""
    v = version_valida(esc, anio)
    SeccionMemoria.objects.filter(version=v).delete()
    return v


def v008(version):
    res = validar_version(version, cfg=cfg_demo(), hoy=HOY)
    return [i for i in res.incidencias if i.codigo == "V-008"]


# ------------------------------------------------------------------ configuración


def test_se_siembran_las_seis_secciones_propuestas(db) -> None:
    asegurar_configuracion(False)
    claves = list(
        SeccionMemoriaCfg.objects.filter(es_demo=False)
        .order_by("orden")
        .values_list("clave", flat=True)
    )
    assert claves == ["resumen", "contexto", "criterios", "riesgos", "cumplimiento", "acuerdo"]
    p = parametros_actuales(False)
    assert p.variaciones_destacadas == 5 and p.saldo_minimo is None
    assert p.marcas_pendiente == ("[COMPLETAR", "PENDIENTE DE REVISAR")
    assert p.seccion("cumplimiento") and p.seccion("cumplimiento").solo_automatica  # type: ignore[union-attr]


def test_lo_editado_no_se_pisa_al_volver_a_sembrar(db) -> None:
    asegurar_configuracion(False)
    SeccionMemoriaCfg.objects.filter(clave="resumen", es_demo=False).update(titulo="Mi título")
    ParametrosAnexosCfg.objects.filter(es_demo=False).update(variaciones_destacadas=9)
    asegurar_configuracion(False)
    assert SeccionMemoriaCfg.objects.get(clave="resumen", es_demo=False).titulo == "Mi título"
    assert parametros_actuales(False).variaciones_destacadas == 9


def test_la_demo_tiene_su_propio_juego_de_valores_ficticios(db) -> None:
    real, demo = parametros_actuales(False), parametros_actuales(True)
    assert real.saldo_minimo is None and demo.saldo_minimo == Decimal("500.00")
    assert demo.reduccion_ingresos["BAJA"] == Decimal("40")
    assert real.prudente_configurado is False and demo.prudente_configurado is True
    assert SeccionMemoriaCfg.objects.filter(es_demo=True).count() == 6


def test_la_instantanea_de_parametros_es_fiel(db) -> None:
    p = parametros_actuales(True)
    assert ParametrosAnexos.desde_json(p.a_json()) == p


# ---------------------------------------------------------------------------- V-008


def test_sin_memoria_se_bloquea_la_propuesta_y_se_dice_que_falta(esc) -> None:
    v = borrador_sin_memoria(esc)
    incidencias = v008(v)
    assert len(incidencias) == 5  # las 5 escritas a mano; «Cumplimiento» la genera el sistema
    assert all(i.gravedad == "BLOQUEANTE" for i in incidencias)
    assert any("Resumen ejecutivo" in i.mensaje for i in incidencias)
    with pytest.raises(ValidationError, match="V-008"):
        proponer(esc, v)


def test_la_memoria_completa_supera_la_regla(esc) -> None:
    v = version_valida(esc)
    assert v008(v) == []
    assert "V-008" not in codigos(validar(v))


def test_una_marca_de_pendiente_bloquea(esc) -> None:
    v = version_valida(esc)
    an.guardar_seccion(esc.tesorero(), v, "contexto", "Texto largo. " * 20 + "[COMPLETAR: algo]")
    assert any("[COMPLETAR" in i.mensaje for i in v008(v))


def test_el_minimo_de_caracteres_se_exige(esc) -> None:
    v = version_valida(esc)
    an.guardar_seccion(esc.tesorero(), v, "contexto", "Corto.")
    assert any("al menos" in i.mensaje for i in v008(v))
    SeccionMemoriaCfg.objects.filter(clave="contexto", es_demo=True).update(longitud_minima=None)
    assert v008(v) == []


def test_una_seccion_opcional_vacia_no_bloquea_pero_con_marca_si(esc) -> None:
    v = version_valida(esc)
    SeccionMemoriaCfg.objects.filter(clave="riesgos", es_demo=True).update(obligatoria=False)
    SeccionMemoria.objects.filter(version=v, clave="riesgos").delete()
    assert v008(v) == []
    an.guardar_seccion(esc.tesorero(), v, "riesgos", "[COMPLETAR: pendiente]")
    assert any("[COMPLETAR" in i.mensaje for i in v008(v))


def test_una_seccion_desactivada_deja_de_pedirse(esc) -> None:
    v = borrador_sin_memoria(esc)
    SeccionMemoriaCfg.objects.filter(es_demo=True).exclude(clave="cumplimiento").update(
        activa=False
    )
    assert v008(v) == []


def test_la_seccion_de_campana_solo_se_pide_con_proceso_electoral(esc) -> None:
    sin = version_valida(esc, 2062)
    con = version_valida(esc, 2063, campana=True)
    SeccionMemoriaCfg.objects.create(
        clave="campana",
        titulo="Plan de campaña",
        orden=7,
        solo_con_proceso_electoral=True,
        longitud_minima=10,
        es_demo=True,
    )
    assert v008(sin) == []
    assert any("Plan de campaña" in i.mensaje for i in v008(con))


def test_texto_sin_cumplimiento_manual_no_se_puede_escribir(esc) -> None:
    v = version_valida(esc)
    with pytest.raises(ValidationError, match="la genera el sistema"):
        an.guardar_seccion(esc.tesorero(), v, "cumplimiento", "Lo escribo yo")
    with pytest.raises(ValidationError, match="no existe"):
        an.guardar_seccion(esc.tesorero(), v, "inventada", "x")


# --------------------------------------------------------------- permisos y sellado


def test_solo_el_tesorero_escribe_y_solo_en_borrador(esc) -> None:
    v = version_valida(esc)
    with pytest.raises(PermissionDenied):
        an.guardar_seccion(esc.vocal(0), v, "resumen", "x" * 200)
    with pytest.raises(PermissionDenied):
        an.guardar_seccion(esc.la_junta(), v, "resumen", "x" * 200)
    proponer(esc, v)
    v.refresh_from_db()
    from apps.presupuesto.errores import VersionNoEditable

    with pytest.raises(VersionNoEditable):
        an.guardar_seccion(esc.tesorero(), v, "resumen", "x" * 200)


def test_la_auditoria_no_guarda_el_texto_de_la_memoria(esc) -> None:
    v = version_valida(esc)
    an.guardar_seccion(esc.tesorero(), v, "contexto", "Habló con Pepito Pérez. " * 10)
    registro = RegistroAuditoria.objects.filter(accion="memoria.guardar_seccion").latest("id")
    assert "Pepito" not in str(registro.antes) + str(registro.despues)
    despues = dict(registro.despues or {})
    assert despues["seccion"] == "contexto" and despues["caracteres"] > 0


def test_guardar_una_seccion_la_da_por_revisada(esc) -> None:
    v = version_valida(esc)
    SeccionMemoria.objects.filter(version=v, clave="resumen").update(pendiente_revision=True)
    assert any("pendiente de revisar" in p for p in problemas_memoria(v))
    an.guardar_seccion(esc.tesorero(), v, "resumen", "Revisado. " * 30)
    assert problemas_memoria(v) == []


def test_la_memoria_forma_parte_de_la_huella(esc) -> None:
    v = version_valida(esc)
    antes = calcular_hash(v)
    an.guardar_seccion(esc.tesorero(), v, "contexto", "Otro texto distinto. " * 20)
    assert calcular_hash(v) != antes
    otra = calcular_hash(v)
    an.guardar_saldo_inicial(esc.tesorero(), v, Decimal("123"))
    assert calcular_hash(v) != otra  # el saldo inicial también


def test_proponer_sella_con_la_huella_nueva_y_guarda_la_instantanea(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    v.refresh_from_db()
    assert v.version_huella == 2 and verificar_integridad(v).ok
    t = v.transiciones.get()
    guardado = dict(t.validacion or {})
    assert guardado["parametros_anexos"]["secciones"][0]["clave"] == "resumen"
    assert guardado["parametros_legales"]
    assert "memoria" in contenido_canonico(v) and "tesoreria" in contenido_canonico(v)


def test_las_versiones_selladas_con_la_huella_antigua_se_siguen_verificando(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE presupuesto_versionpresupuesto DISABLE TRIGGER flujo_version")
        cursor.execute(
            "UPDATE presupuesto_versionpresupuesto SET version_huella = 1 WHERE id = %s", [v.pk]
        )
        v.refresh_from_db()
        cursor.execute(
            "UPDATE presupuesto_versionpresupuesto SET hash = %s WHERE id = %s",
            [calcular_hash(v), v.pk],
        )
    v.refresh_from_db()
    assert "memoria" not in contenido_canonico(v)
    # el estado de la versión ya no coincide con la cadena de transiciones: solo el contenido
    problemas = verificar_integridad(v).problemas
    assert not any("NO coincide" in p for p in problemas)


def test_la_memoria_sellada_se_muestra_con_la_configuracion_con_la_que_se_sello(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    SeccionMemoriaCfg.objects.filter(clave="resumen", es_demo=True).update(titulo="Título nuevo")
    v.refresh_from_db()
    assert parametros_de_version(v).seccion("resumen").titulo == "Resumen ejecutivo"  # type: ignore[union-attr]
    assert parametros_actuales(True).seccion("resumen").titulo == "Título nuevo"  # type: ignore[union-attr]


# ------------------------------------------------------------ inmutabilidad en SQL


def sql_falla(sql: str, params: tuple = ()) -> None:
    with pytest.raises(DatabaseError, match="solo lectura"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(sql, params)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE anexos_seccionmemoria SET texto = 'cambiado' WHERE version_id = %s",
        "DELETE FROM anexos_seccionmemoria WHERE version_id = %s",
        "UPDATE presupuesto_versionpresupuesto SET saldo_inicial_tesoreria = 1 WHERE id = %s",
        "UPDATE presupuesto_versionpresupuesto SET version_huella = 1 WHERE id = %s",
    ],
)
def test_la_memoria_y_el_saldo_de_una_version_sellada_no_se_tocan_ni_con_sql(esc, sql) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    sql_falla(sql, (v.pk,))


def test_no_se_puede_insertar_una_seccion_en_una_version_sellada(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    with pytest.raises(DatabaseError, match="solo lectura"), transaction.atomic():
        SeccionMemoria.objects.create(version=v, clave="nueva", texto="x")


# ---------------------------------------------------------- copias entre versiones


def test_una_modificacion_hereda_la_memoria_pero_pendiente_de_revisar(esc) -> None:
    v = version_valida(esc)
    aprobar_cp(esc, v)
    ratificar(esc, v)
    nueva = fs.crear_modificacion(esc.tesorero(), v, "Cambio de prueba")
    copiadas = SeccionMemoria.objects.filter(version=nueva)
    assert copiadas.count() == 5 and all(s.pendiente_revision for s in copiadas)
    assert nueva.saldo_inicial_tesoreria == v.saldo_inicial_tesoreria
    problemas = problemas_memoria(nueva)
    assert len(problemas) == 5 and all("pendiente de revisar" in p for p in problemas)
    for clave in ("resumen", "contexto", "criterios", "riesgos", "acuerdo"):
        an.guardar_seccion(esc.tesorero(), nueva, clave, "Texto revisado. " * 20)
    assert problemas_memoria(nueva) == []


def test_una_prorroga_hereda_la_memoria_pero_no_el_saldo_inicial(esc) -> None:
    v = version_valida(esc, 2064)
    aprobar_cp(esc, v)
    ratificar(esc, v)
    ej, _ = ps.crear_ejercicio(esc.tesorero(), anio=2065, es_demo=True)
    from datetime import date

    nueva = fs.crear_prorroga(esc.tesorero(), ej, hoy=date(2065, 1, 2))
    assert SeccionMemoria.objects.filter(version=nueva, pendiente_revision=True).count() == 5
    assert nueva.saldo_inicial_tesoreria is None


# ---------------------------------------------------------- contenido automático


def test_la_plantilla_rellena_las_cifras_y_respeta_lo_desconocido(esc) -> None:
    v = version_valida(esc)
    cfg = parametros_actuales(True).seccion("resumen")
    assert cfg is not None
    texto = texto_inicial(cfg, v)
    assert "para 2060" in texto and "[COMPLETAR" in texto and "{" not in texto
    from dataclasses import replace

    rara = replace(cfg, plantilla="Año {ejercicio} {inventado} y una llave { suelta")
    assert texto_inicial(rara, v)  # no falla: se ofrece el texto (con o sin los marcadores)
    assert "{inventado}" in texto_inicial(replace(cfg, plantilla="{inventado} {ejercicio}"), v)
    vacia = replace(cfg, plantilla="")
    assert texto_inicial(vacia, v) == ""


def test_el_resumen_destaca_las_mayores_variaciones(esc) -> None:
    v = version_valida(esc)
    from apps.presupuesto.models import Linea

    Linea.objects.filter(version=v, partida__codigo="G.2.1").update(
        importe_ejercicio_anterior=Decimal("4000")
    )
    Linea.objects.filter(version=v, partida__codigo="I.1.1").update(
        importe_ejercicio_anterior=Decimal("6000")
    )  # igual: no es variación
    b = bloque_resumen(v, parametros_actuales(True))
    assert len(b["variaciones"]) == 1 and b["variaciones"][0]["diferencia"] == Decimal("800")
    assert b["variaciones"][0]["porcentaje"] == Decimal("20.0")
    assert b["ingresos"] == Decimal("11800") and b["gastos"] == Decimal("7800")


def test_el_bloque_de_hipotesis_agrupa_por_capitulo(esc) -> None:
    v = version_valida(esc)
    capitulos = bloque_hipotesis(v)
    assert [c["capitulo"].codigo for c in capitulos][:2] == ["I.1", "I.2"]
    assert sum(len(c["lineas"]) for c in capitulos) == 6


def test_el_bloque_de_riesgos_detecta_la_confianza_baja(esc) -> None:
    v = version_valida(esc)
    b = bloque_riesgos(v)
    assert [ln.codigo for ln in b["baja"]] == ["I.4.1.01"]
    assert b["total_baja"] == Decimal("1000") and str(b["porcentaje_baja"]) == "8.5"


def test_la_seccion_de_cumplimiento_usa_la_instantanea_al_estar_sellada(esc) -> None:
    v = version_valida(esc)
    viva = construir_memoria(v).secciones[4].auto
    assert "ahora mismo" in viva["origen"] and len(viva["superadas"]) == 21
    proponer(esc, v)
    v.refresh_from_db()
    sellada = construir_memoria(v).secciones[4].auto
    assert "momento de proponer" in sellada["origen"]
    assert sellada["avisos_aceptados"] == [] and sellada["incidencias"] == []
    assert all(p["clave"] for p in sellada["parametros"])


def test_estado_de_secciones_marca_las_incompletas(esc) -> None:
    v = borrador_sin_memoria(esc)
    estados = {e.cfg.clave: e for e in estado_secciones(v)}
    assert not estados["resumen"].completa and estados["cumplimiento"].completa
