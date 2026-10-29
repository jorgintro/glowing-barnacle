from pathlib import Path

import pytest

from apps.presupuesto import configuracion as cfg
from apps.presupuesto.models import Capitulo, CuentaPGC, ParametroLegal, Partida
from apps.presupuesto.sincronizacion import sincronizar_todo


def _config(tmp_path: Path, nombre: str, texto: str) -> Path:
    (tmp_path / nombre).write_text(texto, encoding="utf-8")
    return tmp_path


def test_cuadro_real_es_valido_y_tiene_13_capitulos() -> None:
    c = cfg.cargar_cuadro_cuentas()
    assert [x.codigo for x in c.capitulos if x.tipo == "INGRESO"] == [f"I.{i}" for i in range(1, 6)]
    assert [x.codigo for x in c.capitulos if x.tipo == "GASTO"] == [f"G.{i}" for i in range(1, 9)]
    assert not c.validado  # el Tesorero aún no lo ha validado


def test_parametros_legales_reales_estan_todos_pendientes() -> None:
    p = cfg.cargar_parametros_legales()
    assert len(p.parametros) >= 7
    assert all(x.valor is None and x.verificador == "" for x in p.parametros)


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
    assert Capitulo.objects.count() == 13
    assert Partida.objects.get(codigo="G.7.1").dimension_por_defecto == "CAMPANA"
    assert CuentaPGC.objects.filter(codigo="720").exists()
    assert ParametroLegal.objects.filter(valor__isnull=False).count() == 0
    assert not any(p.verificado for p in ParametroLegal.objects.all())


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
    assert Capitulo.objects.count() == 13
    assert Capitulo.objects.get(codigo="G.1").activo is False
    assert Capitulo.objects.get(codigo="I.1").activo is True
