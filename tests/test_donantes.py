from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.servicios import Contexto
from apps.presupuesto import donantes as dn
from apps.presupuesto.configuracion import (
    ErrorConfiguracion,
    cargar_configuracion,
    cargar_cuadro_cuentas,
    cargar_parametros_internos,
)
from apps.presupuesto.errores import RegistroNoBorrable, VersionNoEditable
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import Donacion, Donante, TipoPersona
from apps.presupuesto.nif import normalizar_nif, validar_nif
from apps.usuarios.roles import Rol
from tests.conftest import crear, poner_estado
from tests.util_validaciones import donante, linea, nif

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------------- NIF


@pytest.mark.parametrize(
    "bueno", ["12345678Z", "00000000T", "00000001R", "x1234567l", "12.345.678-z", " 12345678Z "]
)
def test_nif_valido(bueno: str) -> None:
    assert validar_nif(bueno, "FISICA") == normalizar_nif(bueno)


@pytest.mark.parametrize(
    "malo", ["12345678A", "1234567Z", "123456789", "ABCDEFGHI", "", "X1234567A", "12345678"]
)
def test_nif_invalido(malo: str) -> None:
    with pytest.raises(ValidationError):
        validar_nif(malo, "FISICA")


def test_nie_con_letra_de_control() -> None:
    assert validar_nif("X0000000T", "FISICA") == "X0000000T"  # X → 0
    assert validar_nif("Y0000000Z", "FISICA") == "Y0000000Z"  # Y → 1: 10000000 % 23 = 14 → Z


def test_cif_de_persona_juridica_solo_valida_el_formato() -> None:
    assert validar_nif("b12345674", "JURIDICA") == "B12345674"
    for malo in ("12345678Z", "B1234567", "Ñ12345674"):
        with pytest.raises(ValidationError):
            validar_nif(malo, "JURIDICA")


# --------------------------------------------------------------------- donantes


def test_crear_donante_y_auditoria_sin_datos_personales(catalogo, ctx_tesorero: Contexto) -> None:
    d = dn.crear_donante(ctx_tesorero, nombre="  Ana Ficticia ", nif="12345678z")
    assert (
        d.nombre == "Ana Ficticia" and d.nif == "12345678Z" and d.tipo_persona == TipoPersona.FISICA
    )
    reg = RegistroAuditoria.objects.get(accion="donante.crear")
    assert "Ana" not in str(reg.despues) and "12345678" not in str(
        reg.despues
    )  # no se puede borrar
    assert reg.entidad_id == str(d.pk)


def test_donante_con_nif_repetido_o_datos_malos(catalogo, ctx_tesorero: Contexto) -> None:
    dn.crear_donante(ctx_tesorero, nombre="A", nif="12345678Z")
    with pytest.raises(ValidationError, match="Ya existe"):
        dn.crear_donante(ctx_tesorero, nombre="B", nif="12345678Z")
    with pytest.raises(ValidationError):
        dn.crear_donante(ctx_tesorero, nombre=" ", nif="00000001R")
    with pytest.raises(ValidationError):
        dn.crear_donante(ctx_tesorero, nombre="C", nif="00000001R", tipo_persona="OTRA")
    with pytest.raises(ValidationError):
        dn.crear_donante(ctx_tesorero, nombre="D", nif="00000001A")


def test_solo_el_tesorero_gestiona_donantes(catalogo) -> None:
    cp = crear("cp", Rol.COMISION_PERMANENTE)
    ctx = Contexto(cp, Rol.COMISION_PERMANENTE)
    with pytest.raises(PermissionDenied):
        dn.crear_donante(ctx, nombre="X", nif="12345678Z")


def test_baja_de_donante_exige_motivo_y_no_borra(catalogo, ctx_tesorero: Contexto) -> None:
    d = donante(ctx_tesorero, 1)
    with pytest.raises(ValidationError):
        dn.dar_de_baja_donante(ctx_tesorero, d, " ")
    dn.dar_de_baja_donante(ctx_tesorero, d, "Retira su consentimiento")
    d.refresh_from_db()
    assert not d.activo and Donante.objects.filter(pk=d.pk).exists()


# ------------------------------------------------------------------- donaciones


def test_registrar_y_anular_donacion(borrador, ctx_tesorero: Contexto) -> None:
    ln = linea(ctx_tesorero, borrador, "I.4.1", "500", confianza="BAJA")
    d = donante(ctx_tesorero, 1)
    don = dn.registrar_donacion(ctx_tesorero, borrador, ln, d, Decimal("123.456"))
    assert don.importe == Decimal("123.46")
    assert dn.acumulado_anual(borrador) == {d: Decimal("123.46")}
    with pytest.raises(ValidationError):
        dn.anular_donacion(ctx_tesorero, don, "")
    dn.anular_donacion(ctx_tesorero, don, "Error de importe")
    assert dn.acumulado_anual(borrador) == {}
    assert Donacion.objects.filter(pk=don.pk, anulada=True).exists()
    with pytest.raises(RegistroNoBorrable):
        don.delete()


def test_el_acumulado_anual_suma_por_donante_y_ordena(borrador, ctx_tesorero: Contexto) -> None:
    a, b = donante(ctx_tesorero, 1), donante(ctx_tesorero, 2)
    l1 = linea(ctx_tesorero, borrador, "I.4.1", "500", confianza="BAJA")
    l2 = linea(ctx_tesorero, borrador, "I.2.1", "500", confianza="BAJA")
    dn.registrar_donacion(ctx_tesorero, borrador, l1, a, Decimal("100"))
    dn.registrar_donacion(ctx_tesorero, borrador, l2, a, Decimal("50"))
    dn.registrar_donacion(ctx_tesorero, borrador, l1, b, Decimal("200"))
    acum = dn.acumulado_anual(borrador)
    assert list(acum.items()) == [(b, Decimal("200.00")), (a, Decimal("150.00"))]


@pytest.mark.parametrize(
    ("partida", "importe", "baja", "texto"),
    [
        ("I.1.1", "10", False, "Solo se registran"),  # cuotas: no admiten donantes
        ("G.2.1", "10", False, "Solo se registran"),
        ("I.4.1", "0", False, "mayor que cero"),
        ("I.4.1", "-5", False, "mayor que cero"),
        ("I.4.1", "10", True, "de baja"),
    ],
)
def test_donaciones_incorrectas_se_rechazan(
    borrador, ctx_tesorero: Contexto, partida: str, importe: str, baja: bool, texto: str
) -> None:
    ln = linea(
        ctx_tesorero, borrador, partida, "100", confianza="BAJA" if partida.startswith("I") else ""
    )
    d = donante(ctx_tesorero, 1)
    if baja:
        dn.dar_de_baja_donante(ctx_tesorero, d, "baja")
    with pytest.raises(ValidationError, match=texto):
        dn.registrar_donacion(ctx_tesorero, borrador, ln, d, Decimal(importe))


def test_donacion_en_linea_de_otra_version_o_anulada(borrador, ctx_tesorero: Contexto) -> None:
    from apps.presupuesto import servicios as ps

    _, otra = ps.crear_ejercicio(ctx_tesorero, anio=2060)
    ajena = linea(ctx_tesorero, otra, "I.4.1", "100", confianza="BAJA")
    d = donante(ctx_tesorero, 1)
    with pytest.raises(ValidationError):
        dn.registrar_donacion(ctx_tesorero, borrador, ajena, d, Decimal("10"))
    propia = linea(ctx_tesorero, borrador, "I.4.1", "100", confianza="BAJA")
    ps.anular_linea(ctx_tesorero, propia, "duplicada")
    with pytest.raises(ValidationError):
        dn.registrar_donacion(ctx_tesorero, borrador, propia, d, Decimal("10"))


def test_version_no_borrador_no_admite_donaciones(borrador, ctx_tesorero: Contexto) -> None:
    ln = linea(ctx_tesorero, borrador, "I.4.1", "100", confianza="BAJA")
    d = donante(ctx_tesorero, 1)
    don = dn.registrar_donacion(ctx_tesorero, borrador, ln, d, Decimal("10"))
    poner_estado(borrador, EstadoVersion.PROPUESTO)
    with pytest.raises(VersionNoEditable):
        dn.registrar_donacion(ctx_tesorero, borrador, ln, d, Decimal("10"))
    with pytest.raises(VersionNoEditable):
        dn.anular_donacion(ctx_tesorero, don, "motivo")
    with pytest.raises(VersionNoEditable):
        dn.guardar_resultado(
            ctx_tesorero,
            borrador,
            explicacion="x",
            plan_financiacion="",
            endeudamiento=Decimal("0"),
        )


def test_guardar_resultado_audita_y_valida(borrador, ctx_tesorero: Contexto) -> None:
    with pytest.raises(ValidationError):
        dn.guardar_resultado(
            ctx_tesorero,
            borrador,
            explicacion="x",
            plan_financiacion="",
            endeudamiento=Decimal("-1"),
        )
    dn.guardar_resultado(
        ctx_tesorero,
        borrador,
        explicacion=" Superávit ",
        plan_financiacion="Plan",
        endeudamiento=Decimal("10.5"),
    )
    borrador.refresh_from_db()
    assert (
        borrador.explicacion_resultado == "Superávit"
        and borrador.endeudamiento_previsto == Decimal("10.50")
    )
    assert RegistroAuditoria.objects.filter(accion="version.guardar_resultado").exists()


# ------------------------------------------------------------------ configuración


def test_la_estructura_del_cuadro_demo_coincide_con_la_real() -> None:
    """La copia de demostración no debe desviarse del cuadro real (solo cambia la validación)."""
    real, demo = cargar_cuadro_cuentas(), cargar_configuracion(True).cuadro

    def estructura(c):
        return (
            [(x.codigo, x.denominacion) for x in c.cuentas],
            [
                (
                    k.codigo,
                    k.tipo,
                    k.solo_con_proceso_electoral,
                    [(p.codigo, p.cuentas, p.dimension) for p in k.partidas],
                )
                for k in c.capitulos
            ],
        )

    assert estructura(real) == estructura(demo)
    assert not real.validado and demo.validado


def test_ninguna_configuracion_real_trae_valores_inventados_ni_verificados() -> None:
    real = cargar_configuracion(False)
    assert sum(bool(p.verificador) for p in real.legales.values()) == 9  # solo los declarados
    # 9 declarados por el Tesorero + 16 electorales del extracto del 30/10/2026 (sin firma)
    assert sum(p.valor is not None for p in real.legales.values()) == 25
    assert real.internos.umbral_variacion_porcentaje is None
    assert (
        real.organicas.quorum,
        real.organicas.mayoria,
        real.organicas.proponente_puede_votar,
    ) == (None, None, None)


def test_toda_la_configuracion_demo_es_visiblemente_ficticia() -> None:
    demo = cargar_configuracion(True)
    for p in demo.legales.values():
        assert "FICTICIO" in p.referencia_normativa and "ficticio" in p.verificador.lower()
        assert "FICTICIO" in p.descripcion


@pytest.mark.parametrize(
    "texto",
    [
        "umbral_variacion_porcentaje: 20.5",
        "umbral_variacion_porcentaje: abc",
        "umbral_variacion_porcentaje: '-1'",
        "exigir_ventana_verificacion: quizas",
    ],
)
def test_parametros_internos_mal_escritos(tmp_path, texto: str) -> None:
    (tmp_path / "parametros_internos.yaml").write_text(texto, encoding="utf-8")
    with pytest.raises(ErrorConfiguracion):
        cargar_parametros_internos(tmp_path)


def test_parametros_internos_correctos(tmp_path) -> None:
    (tmp_path / "parametros_internos.yaml").write_text(
        "umbral_variacion_porcentaje: '20'", encoding="utf-8"
    )
    c = cargar_parametros_internos(tmp_path)
    assert c.umbral_variacion_porcentaje == Decimal("20") and c.exigir_ventana_verificacion is True


def test_una_version_real_usa_la_config_real_y_una_demo_la_demo(borrador) -> None:
    from apps.validaciones.motor import validar_version

    assert not borrador.es_demo
    res = validar_version(borrador)  # sin cfg: elige por es_demo
    assert not res.puede_avanzar and "L-007" in res.codigos_incumplidos()
    assert nif(1)  # el generador de NIF de pruebas produce algo
