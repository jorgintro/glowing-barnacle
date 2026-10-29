from datetime import date
from typing import Any

import pytest

from apps.presupuesto.configuracion import (
    ErrorConfiguracion,
    Fraccion,
    MayoriaCfg,
    ReglasOrganicasCfg,
    cargar_reglas_organicas,
)
from apps.validaciones.motor import validar_ratificacion, validar_votacion
from apps.validaciones.reglas_o import DatosRatificacion, DatosVotacion, o001, o002, o003, o004
from apps.validaciones.tipos import Gravedad

HOY = date(2026, 10, 29)
SIN_CONFIGURAR = ReglasOrganicasCfg(None, None, None)


_QUORUM = Fraccion(1, 2, True)
_SIMPLE = MayoriaCfg("SIMPLE")


def cfg(quorum=_QUORUM, mayoria=_SIMPLE, puede=None) -> ReglasOrganicasCfg:
    return ReglasOrganicasCfg(quorum, mayoria, puede)


def votacion(**kw) -> DatosVotacion:
    base: dict[str, Any] = dict(miembros=9, asistentes=6, a_favor=4, en_contra=1, abstenciones=1)
    base.update(kw)
    return DatosVotacion(**base)


# ----------------------------------------------------------------------- O-001


def test_o001_sin_configurar_bloquea_la_votacion() -> None:
    inc = o001(votacion(), SIN_CONFIGURAR)
    assert (
        len(inc) == 1
        and "sin configurar" in inc[0].mensaje
        and inc[0].gravedad == Gravedad.BLOQUEANTE
    )
    assert o001(votacion(), cfg(quorum=None)) and o001(votacion(), cfg(mayoria=None))


def test_o001_cumple_quorum_y_mayoria_simple() -> None:
    assert o001(votacion(), cfg()) == []


def test_o001_sin_quorum() -> None:
    inc = o001(
        votacion(asistentes=4, a_favor=3, en_contra=1, abstenciones=0), cfg()
    )  # 4 de 9 no es más de la mitad
    assert any("No hay quórum" in i.mensaje for i in inc)


@pytest.mark.parametrize(
    ("asistentes", "estricto", "hay_quorum"),
    [(4, False, False), (5, False, True), (5, True, True), (4, True, False)],
)
def test_o001_quorum_limites(asistentes: int, estricto: bool, hay_quorum: bool) -> None:
    c = cfg(quorum=Fraccion(1, 2, estricto))
    v = votacion(miembros=9, asistentes=asistentes, a_favor=asistentes, en_contra=0, abstenciones=0)
    assert (not any("quórum" in i.mensaje for i in o001(v, c))) is hay_quorum
    # y con un número par de miembros: la mitad exacta solo vale si no es estricto
    par = votacion(miembros=8, asistentes=4, a_favor=4, en_contra=0, abstenciones=0)
    assert (o001(par, cfg(quorum=Fraccion(1, 2, False))) == []) and bool(
        o001(par, cfg(quorum=Fraccion(1, 2, True)))
    )


def test_o001_mayoria_simple_empate_no_aprueba() -> None:
    inc = o001(votacion(a_favor=2, en_contra=2, abstenciones=2), cfg())
    assert any("mayoría simple" in i.mensaje for i in inc)


@pytest.mark.parametrize(
    ("base", "a_favor", "en_contra", "abst", "asist", "ok"),
    [
        ("ASISTENTES", 4, 1, 1, 6, True),  # 4/6 = 2/3 (al menos)
        ("ASISTENTES", 3, 3, 0, 6, False),
        ("EMITIDOS", 4, 2, 0, 6, True),
        ("EMITIDOS", 3, 1, 2, 6, False),  # 3/6 < 2/3
        ("EMITIDOS_SIN_ABSTENCIONES", 3, 1, 2, 6, True),  # 3/4 ≥ 2/3
        ("MIEMBROS", 6, 0, 0, 9, True),  # 6/9 = 2/3
        ("MIEMBROS", 5, 0, 1, 9, False),
    ],
)
def test_o001_mayoria_cualificada_segun_la_base(base, a_favor, en_contra, abst, asist, ok) -> None:
    c = cfg(mayoria=MayoriaCfg("FRACCION", base, Fraccion(2, 3, False)))
    v = votacion(
        miembros=9, asistentes=asist, a_favor=a_favor, en_contra=en_contra, abstenciones=abst
    )
    assert (o001(v, c) == []) is ok


def test_o001_mayoria_estricta_exige_mas_de_la_fraccion() -> None:
    v = votacion(miembros=9, asistentes=6, a_favor=4, en_contra=2, abstenciones=0)
    assert o001(v, cfg(mayoria=MayoriaCfg("FRACCION", "ASISTENTES", Fraccion(2, 3, False)))) == []
    assert o001(v, cfg(mayoria=MayoriaCfg("FRACCION", "ASISTENTES", Fraccion(2, 3, True))))


def test_o001_recuentos_incoherentes() -> None:
    assert o001(votacion(asistentes=10), cfg())  # más asistentes que miembros
    assert o001(votacion(a_favor=5, en_contra=1, abstenciones=1), cfg())  # más votos que asistentes
    assert o001(votacion(a_favor=-1), cfg())
    assert o001(votacion(miembros=0, asistentes=0, a_favor=0, en_contra=0, abstenciones=0), cfg())


def test_o001_base_cero_no_aprueba() -> None:
    c = cfg(mayoria=MayoriaCfg("FRACCION", "EMITIDOS", Fraccion(1, 2, False)))
    assert o001(votacion(miembros=9, asistentes=5, a_favor=0, en_contra=0, abstenciones=0), c)


# ----------------------------------------------------------------------- O-002


def acta(**kw) -> DatosRatificacion:
    base: dict[str, Any] = dict(
        fecha=date(2026, 11, 20), resultado="RATIFICADO", referencia_acta="Acta 3/2026"
    )
    base.update(kw)
    return DatosRatificacion(**base)


def test_o002_ratificacion_completa_es_valida() -> None:
    assert o002(acta(), date(2026, 11, 21)) == []
    assert o002(acta(resultado="RECHAZADO"), date(2026, 11, 21)) == []


@pytest.mark.parametrize(
    ("cambio", "texto"),
    [
        ({"fecha": None}, "fecha de la sesión"),
        ({"referencia_acta": "  "}, "referencia al acta"),
        ({"resultado": "TAL VEZ"}, "RATIFICADO o RECHAZADO"),
        ({"resultado": ""}, "RATIFICADO o RECHAZADO"),
        ({"fecha": date(2026, 12, 31)}, "futura"),
        ({"fecha_aprobacion_cp": date(2026, 11, 25)}, "antes de la aprobación"),
    ],
)
def test_o002_datos_incompletos_o_incoherentes_bloquean(cambio: dict, texto: str) -> None:
    inc = o002(acta(**cambio), date(2026, 11, 21))
    assert any(texto in i.mensaje for i in inc) and all(
        i.gravedad == Gravedad.BLOQUEANTE for i in inc
    )


# ----------------------------------------------------------------------- O-003


def test_o003_el_proponente_no_puede_votar_si_el_reglamento_lo_impide() -> None:
    v = votacion(proponente=7, votantes=(1, 7, 8))
    assert o003(v, cfg(puede=False)) and "no puede votar" in o003(v, cfg(puede=False))[0].mensaje


def test_o003_sin_configurar_se_aplica_la_opcion_prudente() -> None:
    assert o003(votacion(proponente=7, votantes=(7,)), cfg(puede=None))


def test_o003_si_el_reglamento_lo_permite_vota() -> None:
    assert o003(votacion(proponente=7, votantes=(7,)), cfg(puede=True)) == []


def test_o003_si_no_vota_no_hay_incidencia() -> None:
    assert o003(votacion(proponente=7, votantes=(1, 2)), cfg(puede=False)) == []
    assert o003(votacion(proponente=None, votantes=(1,)), cfg(puede=False)) == []


# ----------------------------------------------------------------------- O-004


def test_o004_convocatoria_anterior_no_avisa() -> None:
    assert o004(acta(fecha_convocatoria=date(2026, 11, 1))) == []
    assert o004(acta(fecha_convocatoria=date(2026, 11, 20))) == []


def test_o004_sin_convocatoria_o_posterior_es_solo_aviso() -> None:
    for r in (acta(fecha_convocatoria=None), acta(fecha_convocatoria=date(2026, 11, 25))):
        inc = o004(r)
        assert len(inc) == 1 and inc[0].gravedad == Gravedad.AVISO


# ------------------------------------------------------------ motor y configuración


def test_el_motor_agrupa_las_reglas_organicas() -> None:
    res = validar_votacion(votacion(proponente=7, votantes=(7,)), cfg(puede=False))
    assert res.codigos_incumplidos() == {"O-003"} and not res.puede_avanzar
    ok = validar_votacion(votacion(), cfg())
    assert ok.puede_avanzar and set(ok.superadas()) == {"O-001", "O-003"}
    rat = validar_ratificacion(acta(fecha=date(2026, 10, 1), fecha_convocatoria=None), HOY)
    assert rat.puede_avanzar and rat.codigos_incumplidos() == {"O-004"}  # solo aviso


def test_la_configuracion_organica_real_esta_sin_rellenar() -> None:
    real = cargar_reglas_organicas()
    assert real.quorum is None and real.mayoria is None and real.proponente_puede_votar is None
    assert o001(votacion(), real)  # por tanto, la votación real está bloqueada


def test_la_configuracion_organica_demo_recoge_las_excepciones_pedidas() -> None:
    from apps.presupuesto.configuracion import cargar_configuracion

    demo = cargar_configuracion(True).organicas
    assert demo.proponente_puede_votar is True
    assert o003(votacion(proponente=7, votantes=(7,)), demo) == []
    assert o001(votacion(), demo) == []


@pytest.mark.parametrize(
    "texto",
    [
        "quorum: {base: ASISTENTES, minimo: '1/2', estricto: true}",
        "quorum: {base: MIEMBROS, minimo: '0.5', estricto: true}",
        "quorum: {base: MIEMBROS, minimo: '3/2', estricto: true}",
        "quorum: {base: MIEMBROS, minimo: '1/0', estricto: true}",
        "quorum: {base: MIEMBROS, minimo: '1/2', estricto: si}",
        "mayoria: {tipo: RARA}",
        "mayoria: {tipo: FRACCION, base: OTRA, minimo: '2/3', estricto: false}",
        "proponente_puede_votar: quizas",
    ],
)
def test_la_configuracion_organica_mal_escrita_se_rechaza(tmp_path, texto: str) -> None:
    (tmp_path / "reglas_organicas.yaml").write_text(texto, encoding="utf-8")
    with pytest.raises(ErrorConfiguracion):
        cargar_reglas_organicas(tmp_path)
