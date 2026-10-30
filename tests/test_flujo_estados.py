"""Proponer, devolver, votar y cerrar la votación (CLAUDE.md §5)."""

from dataclasses import replace
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.servicios import Contexto
from apps.flujo import servicios as fs
from apps.flujo.models import (
    EstadoVotacion,
    ResultadoVotacion,
    TransicionEstado,
    Votacion,
    VotoNominal,
)
from apps.flujo.sello import calcular_hash, verificar_integridad
from apps.presupuesto import donantes as dn
from apps.presupuesto import servicios as ps
from apps.presupuesto.configuracion import Fraccion, MayoriaCfg, cargar_configuracion
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import Linea, TipoOrigen
from apps.usuarios.roles import Rol
from tests.conftest import crear
from tests.util_flujo import (
    A,
    C,
    N,
    aprobar_cp,
    crear_escenario,
    organicas_estrictas,
    proponer,
    version_valida,
    votar_y_cerrar,
)
from tests.util_validaciones import linea, presupuesto_valido

pytestmark = pytest.mark.django_db


@pytest.fixture
def esc(catalogo):
    return crear_escenario()


# ------------------------------------------------------------------------ proponer


def test_proponer_sella_la_version_y_abre_la_votacion(esc) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    v.refresh_from_db()
    assert v.estado == EstadoVersion.PROPUESTO and not v.editable
    assert len(v.hash) == 64 and v.hash == calcular_hash(v) and v.proponente == esc.t
    assert votacion.estado == EstadoVotacion.ABIERTA and votacion.version == v
    t = TransicionEstado.objects.get(version=v)
    assert (t.de_estado, t.a_estado, t.rol) == ("BORRADOR", "PROPUESTO", Rol.TESORERO)
    assert t.hash_version == v.hash and t.hash_previo == "" and len(t.hash_encadenado) == 64
    assert t.validacion is not None
    assert t.validacion["incidencias"] == [] and len(t.validacion["reglas_ejecutadas"]) == 21
    acciones = set(RegistroAuditoria.objects.values_list("accion", flat=True))
    assert {"version.propuesto", "votacion.abrir"} <= acciones
    assert verificar_integridad(v).ok


def test_proponer_exige_ser_tesorero_y_confirmar(esc) -> None:
    v = version_valida(esc)
    with pytest.raises(PermissionDenied):
        fs.proponer(esc.vocal(0), v, confirmar=True)
    with pytest.raises(ValidationError, match="confirmar"):
        fs.proponer(esc.tesorero(), v, confirmar=False)
    v.refresh_from_db()
    assert v.estado == EstadoVersion.BORRADOR and v.hash == ""
    assert not Votacion.objects.exists()


def test_proponer_se_bloquea_si_hay_validaciones_bloqueantes(esc) -> None:
    v = version_valida(esc)
    dn.guardar_resultado(
        esc.tesorero(), v, explicacion="", plan_financiacion="", endeudamiento=Decimal("0")
    )
    with pytest.raises(ValidationError) as error:
        proponer(esc, v)
    assert any("V-006" in m for m in error.value.messages)
    v.refresh_from_db()
    assert v.estado == EstadoVersion.BORRADOR and v.editable
    assert not TransicionEstado.objects.exists() and not Votacion.objects.exists()


def test_los_avisos_hay_que_aceptarlos_y_queda_constancia(esc) -> None:
    v = version_valida(esc)
    alquiler = Linea.objects.get(version=v, partida__codigo="G.2.1")
    Linea.objects.filter(pk=alquiler.pk).update(importe_ejercicio_anterior=Decimal("1000.00"))
    with pytest.raises(ValidationError, match="avisos sin aceptar"):
        fs.proponer(esc.tesorero(), v, avisos_aceptados=[], confirmar=True)
    fs.proponer(esc.tesorero(), v, avisos_aceptados=["V-007"], confirmar=True)
    assert TransicionEstado.objects.get(version=v).avisos_aceptados == ["V-007"]


def test_una_version_real_no_puede_proponerse_sin_parametros_verificados(
    catalogo, tesorero, ctx_tesorero
) -> None:
    """Sin cuadro validado y con parámetros pendientes, ninguna versión REAL avanza."""
    _, v = ps.crear_ejercicio(ctx_tesorero, anio=2061)
    presupuesto_valido(ctx_tesorero, v)
    with pytest.raises(ValidationError) as error:
        fs.proponer(ctx_tesorero, v, avisos_aceptados=["V-007", "L-008"], confirmar=True)
    texto = " ".join(error.value.messages)
    assert "L-006" in texto and "L-007" in texto
    v.refresh_from_db()
    assert v.estado == EstadoVersion.BORRADOR


def test_solo_se_propone_un_borrador(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    with pytest.raises(ValidationError, match="Propuesto"):
        proponer(esc, v)


# ------------------------------------------------------------------------ devolver


def test_la_cp_devuelve_la_propuesta_con_motivos(esc) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    with pytest.raises(PermissionDenied):
        fs.devolver(esc.tesorero(), v, "No me gusta")
    with pytest.raises(ValidationError, match="motivos"):
        fs.devolver(esc.vocal(0), v, "  ")
    fs.devolver(esc.vocal(0), v, "Falta detallar los actos")
    v.refresh_from_db()
    votacion.refresh_from_db()
    assert (
        v.estado == EstadoVersion.BORRADOR and v.editable and v.hash == "" and v.proponente is None
    )
    assert (
        votacion.estado == EstadoVotacion.CERRADA
        and votacion.resultado == ResultadoVotacion.ANULADA
    )
    ultima = TransicionEstado.objects.filter(version=v).latest("id")
    assert ultima.motivo == "Falta detallar los actos" and ultima.rol == Rol.COMISION_PERMANENTE
    # vuelve a ser editable y se puede proponer de nuevo, con la cadena intacta
    linea(esc.tesorero(), v, "G.3.1", "100")
    proponer(esc, v)
    assert verificar_integridad(v).ok and TransicionEstado.objects.filter(version=v).count() == 3


# --------------------------------------------------------------------------- votar


def test_un_miembro_vota_y_puede_cambiar_su_voto_mientras_este_abierta(esc) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    fs.votar(esc.vocal(0), votacion, A)
    fs.votar(esc.vocal(0), votacion, C)
    voto = VotoNominal.objects.get(votacion=votacion, usuario=esc.cp[0])
    assert voto.voto == C and VotoNominal.objects.count() == 1
    acciones = list(
        RegistroAuditoria.objects.filter(accion__startswith="voto.")
        .order_by("id")
        .values_list("accion", flat=True)
    )
    assert acciones == ["voto.emitir", "voto.cambiar"]


def test_solo_votan_los_miembros_de_la_cp_con_ese_rol_activo(esc) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    with pytest.raises(PermissionDenied):  # el Tesorero con su rol de Tesorero no vota
        fs.votar(esc.tesorero(), votacion, A)
    real = crear("cp_real", Rol.COMISION_PERMANENTE)  # no es de demostración
    with pytest.raises(PermissionDenied, match="No eres miembro"):
        fs.votar(Contexto(real, Rol.COMISION_PERMANENTE), votacion, A)
    with pytest.raises(PermissionDenied):
        fs.votar(esc.la_junta(), votacion, A)
    with pytest.raises(ValidationError, match="desconocido"):
        fs.votar(esc.vocal(0), votacion, "TAL_VEZ")
    assert VotoNominal.objects.count() == 0


def test_el_proponente_no_puede_votar_si_el_reglamento_lo_impide(esc, monkeypatch) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    fs.votar(esc.t_como_cp(), votacion, A)  # con la configuración demo sí puede
    organicas_estrictas(monkeypatch)
    with pytest.raises(ValidationError, match="no puede votar"):
        fs.votar(esc.t_como_cp(), votacion, A)
    fs.votar(esc.vocal(0), votacion, A)  # los demás, sí


def test_no_se_vota_en_una_votacion_cerrada(esc) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    votar_y_cerrar(esc, votacion, {0: A, 1: A, 2: A})
    with pytest.raises(ValidationError, match="cerrada"):
        fs.votar(esc.vocal(2), votacion, C)


def test_los_miembros_se_cuentan_por_separado_en_demo_y_real(esc) -> None:
    crear("cp_real", Rol.COMISION_PERMANENTE)
    assert fs.miembros_cp(True).count() == 4 and fs.miembros_cp(False).count() == 1


# --------------------------------------------------------------------------- cerrar


def test_con_quorum_y_mayoria_la_cp_aprueba(esc) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    cerrada = votar_y_cerrar(esc, votacion, {0: A, 1: A, 2: A, 3: N})
    v.refresh_from_db()
    assert v.estado == EstadoVersion.APROBADO_CP and v.requiere_junta is True
    assert (
        cerrada.miembros,
        cerrada.asistentes,
        cerrada.a_favor,
        cerrada.en_contra,
        cerrada.abstenciones,
    ) == (4, 4, 3, 0, 1)
    assert cerrada.resultado == ResultadoVotacion.APROBADA and cerrada.evaluacion["quorum"] is True
    assert cerrada.estado == EstadoVotacion.CERRADA and cerrada.cerrada_por == esc.cp[0]
    assert cerrada.observaciones == "Cierre de prueba"
    pasos = list(TransicionEstado.objects.filter(version=v).values_list("a_estado", flat=True))
    assert pasos == ["PROPUESTO", "APROBADO_CP"] and verificar_integridad(v).ok


def test_sin_quorum_la_votacion_no_se_puede_cerrar_y_sigue_abierta(esc) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    fs.votar(esc.vocal(0), votacion, A)
    fs.votar(esc.vocal(1), votacion, A)  # 2 de 4: no es «más de la mitad»
    with pytest.raises(ValidationError, match="No hay quórum"):
        fs.cerrar_votacion(esc.vocal(0), votacion)
    votacion.refresh_from_db()
    v.refresh_from_db()
    assert votacion.estado == EstadoVotacion.ABIERTA and v.estado == EstadoVersion.PROPUESTO
    fs.votar(esc.vocal(2), votacion, A)  # 3 de 4: ya hay quórum
    fs.cerrar_votacion(esc.vocal(0), votacion)
    v.refresh_from_db()
    assert v.estado == EstadoVersion.APROBADO_CP


def test_con_quorum_pero_sin_mayoria_se_rechaza_y_se_abre_un_nuevo_borrador(esc) -> None:
    v = version_valida(esc)
    n_lineas = Linea.objects.filter(version=v).count()
    votacion = proponer(esc, v)
    cerrada = votar_y_cerrar(esc, votacion, {0: A, 1: C, 2: C, 3: C})
    v.refresh_from_db()
    assert cerrada.resultado == ResultadoVotacion.RECHAZADA and v.estado == EstadoVersion.RECHAZADO
    nuevo = v.ejercicio.versiones.get(numero=2)
    assert nuevo.estado == EstadoVersion.BORRADOR and nuevo.tipo_origen == TipoOrigen.TRAS_RECHAZO
    assert nuevo.version_origen == v and Linea.objects.filter(version=nuevo).count() == n_lineas
    assert nuevo.editable and nuevo.hash == ""


def test_el_rechazo_puede_no_abrir_borrador(esc) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    votar_y_cerrar(esc, votacion, {0: C, 1: C, 2: C, 3: C}, crear_borrador=False)
    assert v.ejercicio.versiones.count() == 1


def test_con_las_reglas_organicas_sin_configurar_la_votacion_queda_bloqueada(
    esc, monkeypatch
) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    for i in range(3):
        fs.votar(esc.vocal(i), votacion, A)
    base = cargar_configuracion(True)
    sin = replace(base, organicas=replace(base.organicas, quorum=None, mayoria=None))
    monkeypatch.setattr("apps.flujo.servicios._cfg", lambda version: sin)
    with pytest.raises(ValidationError, match="sin configurar"):
        fs.cerrar_votacion(esc.vocal(0), votacion)
    votacion.refresh_from_db()
    assert votacion.estado == EstadoVotacion.ABIERTA


def test_la_mayoria_cualificada_de_la_configuracion_se_aplica(esc, monkeypatch) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    base = cargar_configuracion(True)
    dos_tercios = replace(
        base.organicas, mayoria=MayoriaCfg("FRACCION", "ASISTENTES", Fraccion(2, 3, False))
    )
    monkeypatch.setattr(
        "apps.flujo.servicios._cfg", lambda version: replace(base, organicas=dos_tercios)
    )
    cerrada = votar_y_cerrar(esc, votacion, {0: A, 1: A, 2: C, 3: C})  # 2 de 4 asistentes < 2/3
    assert cerrada.resultado == ResultadoVotacion.RECHAZADA


def test_no_se_cierra_dos_veces_ni_por_quien_no_es_de_la_cp(esc) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    with pytest.raises(PermissionDenied):
        fs.cerrar_votacion(esc.tesorero(), votacion)
    votar_y_cerrar(esc, votacion, {0: A, 1: A, 2: A})
    with pytest.raises(ValidationError, match="ya está cerrada"):
        fs.cerrar_votacion(esc.vocal(0), votacion)


def test_si_el_reglamento_cambia_el_proponente_no_puede_haber_votado(esc, monkeypatch) -> None:
    v = version_valida(esc)
    votacion = proponer(esc, v)
    for ctx in (esc.t_como_cp(), esc.vocal(0), esc.vocal(1)):
        fs.votar(ctx, votacion, A)
    organicas_estrictas(monkeypatch)  # ahora el reglamento lo impide
    with pytest.raises(ValidationError, match="no puede votar su aprobación"):
        fs.cerrar_votacion(esc.vocal(0), votacion)


def test_la_cp_puede_comentar_y_se_ve_en_todo_el_proceso(esc) -> None:
    v = version_valida(esc)
    proponer(esc, v)
    c = fs.comentar(
        esc.vocal(0), v, "Revisar la partida de actos", Linea.objects.filter(version=v).first()
    )
    assert c.rol_autor == Rol.COMISION_PERMANENTE and not c.resuelto
    fs.resolver_comentario(esc.tesorero(), c)
    c.refresh_from_db()
    assert c.resuelto and c.resuelto_por == esc.t
    aprobar_cp_votos = {0: A, 1: A, 2: A}
    votar_y_cerrar(esc, Votacion.objects.get(version=v), aprobar_cp_votos)
    fs.comentar(esc.vocal(1), v, "Comentario tras la aprobación")  # los comentarios no son cifras
    assert v.comentarios.count() == 2


def test_comentarios_permisos_y_validaciones(esc) -> None:
    v = version_valida(esc)
    otra = version_valida(esc, anio=2061)
    with pytest.raises(PermissionDenied):
        fs.comentar(esc.la_junta(), v, "x")
    with pytest.raises(ValidationError, match="vacío"):
        fs.comentar(esc.vocal(0), v, "  ")
    ajena = Linea.objects.filter(version=otra).first()
    with pytest.raises(ValidationError, match="no es de esta versión"):
        fs.comentar(esc.vocal(0), v, "texto", ajena)
    c = fs.comentar(esc.tesorero(), v, "Nota del Tesorero")
    fs.resolver_comentario(esc.vocal(0), c)
    fs.resolver_comentario(esc.vocal(0), c)  # idempotente
    assert RegistroAuditoria.objects.filter(accion="comentario.resolver").count() == 1
    with pytest.raises(PermissionDenied):
        fs.resolver_comentario(esc.la_junta(), c)


def test_aprobar_cp_helper_deja_la_version_en_aprobada(esc) -> None:
    v = version_valida(esc)
    aprobar_cp(esc, v)
    assert v.estado == EstadoVersion.APROBADO_CP and ps  # y el módulo de servicios sigue accesible
