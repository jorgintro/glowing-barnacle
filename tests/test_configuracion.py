from pathlib import Path

import pytest

from apps.presupuesto import configuracion as cfg
from apps.presupuesto.models import Capitulo, CuentaPGC, ParametroLegal, Partida
from apps.presupuesto.sincronizacion import sincronizar_todo


def _config(tmp_path: Path, nombre: str, texto: str) -> Path:
    (tmp_path / nombre).write_text(texto, encoding="utf-8")
    return tmp_path


def test_cuadro_real_es_valido_y_tiene_15_capitulos_en_dos_ambitos() -> None:
    c = cfg.cargar_cuadro_cuentas()
    assert [x.codigo for x in c.capitulos if x.tipo == "INGRESO"] == [f"I.{i}" for i in range(1, 8)]
    assert [x.codigo for x in c.capitulos if x.tipo == "GASTO"] == [f"G.{i}" for i in range(1, 9)]
    # dos presupuestos separados: el electoral tiene sus propios capítulos
    electorales = [x.codigo for x in c.capitulos if x.ambito == "ELECTORAL"]
    assert electorales == ["I.6", "I.7", "G.7"]
    assert not c.validado  # el Tesorero aún no lo ha validado


def test_los_nueve_parametros_declarados_verificados_figuran_como_tales() -> None:
    from apps.validaciones.contexto import parametro_verificado

    p = cfg.cargar_parametros_legales()
    assert len(p.parametros) == 27
    verificados = {x.clave for x in p.parametros if parametro_verificado(x)}
    assert len(verificados) == 9
    for x in p.parametros:
        if x.clave in verificados:
            assert "declaración" in x.verificador  # es una declaración del Tesorero, no un hecho
        else:  # sin verificar: sin fecha ni verificador
            assert x.fecha_verificacion is None and x.verificador == ""
        if x.ambito != "ELECTORAL" and x.clave not in verificados:
            assert x.valor is None  # aportaciones de cargos y endeudamiento: no se inventan


def test_los_parametros_electorales_figuran_sin_verificar_y_con_su_origen() -> None:
    """Valores del extracto del 30/10/2026 (elecciones locales de 2023): sin verificar."""
    from apps.validaciones.contexto import parametro_verificado

    por_clave = {x.clave: x for x in cfg.cargar_parametros_legales().parametros}
    electorales = [x for x in por_clave.values() if x.ambito == "ELECTORAL"]
    assert len(electorales) == 16
    assert not any(parametro_verificado(x) for x in electorales)
    assert por_clave["gasto_electoral_euros_por_habitante"].valor == "0.11"
    assert por_clave["gasto_electoral_adicional_por_provincia"].valor == "150301.11"
    assert por_clave["limite_aportacion_electoral_por_persona"].valor == "10000.00"
    assert por_clave["subvencion_electoral_por_concejal"].valor == "270.90"
    assert por_clave["subvencion_electoral_por_voto"].valor == "0.54"
    assert por_clave["subvencion_envio_por_elector"].valor == "0.23"
    assert por_clave["plazo_contabilidad_electoral_hasta_dias"].valor == "125"
    assert all("extracto aportado por el Tesorero" in x.referencia_normativa for x in electorales)
    # los de solo cálculo informativo no condicionan ninguna regla
    assert por_clave["subvencion_electoral_por_voto"].informativo
    assert not por_clave["gasto_electoral_euros_por_habitante"].informativo
    assert not por_clave["limite_aportacion_electoral_por_persona"].informativo


def test_los_valores_del_extracto_de_la_ley_estan_cargados_con_su_referencia() -> None:
    """Valores tomados del texto que aportó el Tesorero; la verificación sigue pendiente."""
    por_clave = {x.clave: x for x in cfg.cargar_parametros_legales().parametros}
    assert por_clave["limite_donacion_anual_por_donante"].valor == "50000.00"
    assert por_clave["donaciones_anonimas_permitidas"].valor is False
    assert por_clave["donaciones_personas_juridicas_permitidas"].valor is False
    assert por_clave["umbral_notificacion_tribunal_cuentas"].valor == "25000.00"
    assert por_clave["umbral_identificacion_actividades_propias"].valor == "300.00"
    assert por_clave["donaciones_contratistas_publicos_permitidas"].valor is False
    assert por_clave["donaciones_finalistas_o_revocables_permitidas"].valor is False
    assert por_clave["donaciones_inmuebles_exentas_de_limite"].valor is True
    assert "ACTIVIDAD_MERCANTIL" in por_clave["fuentes_ingreso_prohibidas"].valor
    for clave in (
        "limite_donacion_anual_por_donante",
        "donaciones_anonimas_permitidas",
        "donaciones_personas_juridicas_permitidas",
        "fuentes_ingreso_prohibidas",
        "umbral_notificacion_tribunal_cuentas",
        "umbral_identificacion_actividades_propias",
        "donaciones_contratistas_publicos_permitidas",
        "donaciones_finalistas_o_revocables_permitidas",
        "donaciones_inmuebles_exentas_de_limite",
    ):
        ref = por_clave[clave].referencia_normativa
        assert "LO 8/2007" in ref and "extracto aportado por el Tesorero" in ref
    # lo que el extracto no dice sigue sin valor (no se inventa)
    for clave in (
        "limite_aportaciones_cargos_anual",
        "limite_endeudamiento",
    ):
        assert por_clave[clave].valor is None and por_clave[clave].referencia_normativa == ""


def test_cuenta_desconocida_se_rechaza(tmp_path: Path) -> None:
    d = _config(
        tmp_path,
        "cuadro_cuentas.yaml",
        """
cuentas: [{codigo: "720", denominacion: "Cuotas"}]
capitulos:
  - codigo: "I.1"
    tipo: INGRESO
    denominacion: Cuotas
    partidas:
      - {codigo: "I.1.1", denominacion: X, cuentas: ["999"]}
""",
    )
    with pytest.raises(cfg.ErrorConfiguracion, match="cuentas no definidas"):
        cfg.cargar_cuadro_cuentas(d)


def test_partida_fuera_de_su_capitulo_se_rechaza(tmp_path: Path) -> None:
    d = _config(
        tmp_path,
        "cuadro_cuentas.yaml",
        """
cuentas: [{codigo: "720", denominacion: "Cuotas"}]
capitulos:
  - codigo: "I.1"
    tipo: INGRESO
    denominacion: Cuotas
    partidas:
      - {codigo: "G.1.1", denominacion: X, cuentas: ["720"]}
""",
    )
    with pytest.raises(cfg.ErrorConfiguracion, match="debe empezar por"):
        cfg.cargar_cuadro_cuentas(d)


def test_importe_decimal_sin_comillas_se_rechaza(tmp_path: Path) -> None:
    d = _config(
        tmp_path,
        "parametros_legales.yaml",
        """
parametros:
  - {clave: x, descripcion: d, unidad: EUR, valor: 1234.56}
""",
    )
    with pytest.raises(cfg.ErrorConfiguracion, match="entre comillas"):
        cfg.cargar_parametros_legales(d)


def test_yaml_roto_o_ausente(tmp_path: Path) -> None:
    with pytest.raises(cfg.ErrorConfiguracion, match="No existe"):
        cfg.cargar_cuadro_cuentas(tmp_path)
    d = _config(tmp_path, "cuadro_cuentas.yaml", "a: [sin cerrar")
    with pytest.raises(cfg.ErrorConfiguracion, match="no es un YAML"):
        cfg.cargar_cuadro_cuentas(d)


@pytest.mark.django_db
def test_sincronizacion_es_idempotente_y_audita() -> None:
    from apps.auditoria.models import RegistroAuditoria

    primera = sincronizar_todo()
    assert primera["cuadro_cuentas"].creados > 0
    n_audit = RegistroAuditoria.objects.filter(accion="config.sincronizar").count()
    assert n_audit == 2
    segunda = sincronizar_todo()
    assert not segunda["cuadro_cuentas"].hubo_cambios
    assert not segunda["parametros_legales"].hubo_cambios
    assert RegistroAuditoria.objects.filter(accion="config.sincronizar").count() == n_audit
    assert Capitulo.objects.count() == 15
    assert Partida.objects.get(codigo="G.7.1").dimension_por_defecto == "CAMPANA"
    assert CuentaPGC.objects.filter(codigo="710").exists()
    assert ParametroLegal.objects.filter(valor__isnull=False).count() == 25  # 9 + 16 electorales
    assert ParametroLegal.objects.filter(ambito="ELECTORAL").count() == 16
    assert Partida.objects.filter(envio_electoral=True).count() == 4  # G.7.11 a G.7.14
    assert (
        sum(p.verificado for p in ParametroLegal.objects.all()) == 9
    )  # declarados por el Tesorero


@pytest.mark.django_db
def test_lo_que_desaparece_del_yaml_se_desactiva_no_se_borra(tmp_path: Path) -> None:
    from apps.presupuesto.sincronizacion import sincronizar_cuadro_cuentas

    sincronizar_cuadro_cuentas()
    d = _config(
        tmp_path,
        "cuadro_cuentas.yaml",
        """
cuentas: [{codigo: "720", denominacion: "Cuotas"}]
capitulos:
  - codigo: "I.1"
    tipo: INGRESO
    denominacion: Cuotas
    partidas:
      - {codigo: "I.1.1", denominacion: X, cuentas: ["720"]}
""",
    )
    r = sincronizar_cuadro_cuentas(cfg.cargar_cuadro_cuentas(d))
    assert r.desactivados > 0
    assert Capitulo.objects.count() == 15
    assert Capitulo.objects.get(codigo="G.1").activo is False
    assert Capitulo.objects.get(codigo="I.1").activo is True


def test_el_cuadro_solo_usa_cuentas_del_plan_contable_de_las_formaciones() -> None:
    """Cada cuenta del cuadro (real y demo) existe en el catálogo aportado, con su denominación."""
    from pathlib import Path

    import yaml
    from django.conf import settings

    base = Path(settings.CONFIG_DIR)
    plan = yaml.safe_load((base / "plan_cuentas_formaciones.yaml").read_text(encoding="utf-8"))
    oficiales = {str(k): v for k, v in plan["cuentas"].items()}
    for ruta in (base, base / "demo"):
        cuadro = cfg.cargar_cuadro_cuentas(ruta)
        for cuenta in cuadro.cuentas:
            assert cuenta.codigo in oficiales, f"{cuenta.codigo} no está en el plan contable"
            assert cuenta.denominacion == oficiales[cuenta.codigo], cuenta.codigo
        # y todas las partidas usan cuentas definidas en el cuadro (lo exige el cargador)
        assert all(p.cuentas for c in cuadro.capitulos for p in c.partidas)


def test_la_estructura_de_la_demo_coincide_con_la_real() -> None:
    real, demo = cfg.cargar_cuadro_cuentas(), cfg.cargar_cuadro_cuentas(cfg.directorio_config(True))
    assert [(c.codigo, c.ambito, [p.codigo for p in c.partidas]) for c in real.capitulos] == [
        (c.codigo, c.ambito, [p.codigo for p in c.partidas]) for c in demo.capitulos
    ]
