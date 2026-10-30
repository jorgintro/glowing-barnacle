"""Ayudas para las pruebas del flujo de aprobación."""

from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.anexos import servicios as anexos
from apps.anexos.models import SeccionMemoria
from apps.auditoria.servicios import Contexto
from apps.flujo import servicios as fs
from apps.flujo.models import Voto
from apps.presupuesto import servicios as ps
from apps.presupuesto.configuracion import ConfiguracionVersion, cargar_configuracion
from apps.presupuesto.models import VersionPresupuesto
from apps.usuarios.models import Usuario
from apps.usuarios.roles import Rol
from tests.conftest import crear
from tests.util_validaciones import presupuesto_valido

A, C, N = Voto.A_FAVOR, Voto.EN_CONTRA, Voto.ABSTENCION


@dataclass
class Escenario:
    """Una organización de demostración: Tesorero (que también es de la CP), 3 vocales y Junta."""

    t: Usuario
    cp: list[Usuario]
    junta: Usuario

    def tesorero(self) -> Contexto:
        return Contexto(self.t, Rol.TESORERO, "127.0.0.1")

    def vocal(self, i: int) -> Contexto:
        return Contexto(self.cp[i], Rol.COMISION_PERMANENTE, "127.0.0.1")

    def t_como_cp(self) -> Contexto:
        return Contexto(self.t, Rol.COMISION_PERMANENTE, "127.0.0.1")

    def la_junta(self) -> Contexto:
        return Contexto(self.junta, Rol.JUNTA_GENERAL, "127.0.0.1")

    @property
    def miembros(self) -> list[Usuario]:
        return [self.t, *self.cp]


def crear_escenario() -> Escenario:
    t = crear("t_demo", Rol.TESORERO, Rol.COMISION_PERMANENTE, es_demo=True)
    cp = [crear(f"cp{i}_demo", Rol.COMISION_PERMANENTE, es_demo=True) for i in (1, 2, 3)]
    junta = crear("junta_demo", Rol.JUNTA_GENERAL, es_demo=True)
    return Escenario(t, cp, junta)


def version_valida(e: Escenario, anio: int = 2060, campana: bool = False) -> VersionPresupuesto:
    """Borrador DEMO (usa la configuración ficticia) que supera todas las reglas."""
    _, v = ps.crear_ejercicio(e.tesorero(), anio=anio, hay_proceso_electoral=campana, es_demo=True)
    presupuesto_valido(e.tesorero(), v, campana=campana)
    return v


def revisar_anexos(e: Escenario, v: VersionPresupuesto) -> None:
    """Lo que haría el Tesorero con una versión copiada: revisar la memoria y poner el saldo."""
    for s in SeccionMemoria.objects.filter(version=v, pendiente_revision=True):
        anexos.guardar_seccion(e.tesorero(), v, s.clave, s.texto)
    if v.saldo_inicial_tesoreria is None and SeccionMemoria.objects.filter(version=v).exists():
        anexos.guardar_saldo_inicial(e.tesorero(), v, Decimal("100000"))


def proponer(e: Escenario, v: VersionPresupuesto):  # type: ignore[no-untyped-def]
    revisar_anexos(e, v)
    return fs.proponer(e.tesorero(), v, avisos_aceptados=["V-007", "L-008"], confirmar=True)


def votar_y_cerrar(e: Escenario, votacion, votos: dict[int, str], **kw: Any):  # type: ignore[no-untyped-def]
    """``votos``: índice (0 = Tesorero como CP, 1-3 = vocales) → voto."""
    for i, voto in votos.items():
        ctx = e.t_como_cp() if i == 0 else e.vocal(i - 1)
        fs.votar(ctx, votacion, voto)
    return fs.cerrar_votacion(e.vocal(0), votacion, "Cierre de prueba", **kw)


def aprobar_cp(e: Escenario, v: VersionPresupuesto):  # type: ignore[no-untyped-def]
    votacion = proponer(e, v)
    votar_y_cerrar(e, votacion, {0: A, 1: A, 2: A, 3: N})
    v.refresh_from_db()
    return votacion


def ratificar(e: Escenario, v: VersionPresupuesto, **kw: Any):  # type: ignore[no-untyped-def]
    hoy = timezone.localdate()
    fs.registrar_convocatoria(
        e.tesorero(), v, fecha_convocatoria=hoy - timedelta(days=5), fecha_sesion=hoy
    )
    datos: dict[str, Any] = {
        "fecha_sesion": hoy,
        "resultado": "RATIFICADO",
        "referencia_acta": "ACTA-PRUEBA",
    }
    datos.update(kw)
    r = fs.registrar_ratificacion(e.la_junta(), v, **datos)
    v.refresh_from_db()
    return r


def vigente(e: Escenario, anio: int = 2060, campana: bool = False) -> VersionPresupuesto:
    """Versión ratificada de principio a fin."""
    v = version_valida(e, anio, campana)
    aprobar_cp(e, v)
    ratificar(e, v)
    return v


def organicas_estrictas(monkeypatch: Any, **cambios: Any) -> ConfiguracionVersion:
    """Sustituye la configuración orgánica de la demo por otra (p. ej. sin excepciones)."""
    base = cargar_configuracion(True)
    org = replace(
        base.organicas,
        ratificacion_registrada_por=("JUNTA_GENERAL",),
        proponente_puede_votar=False,
        **cambios,
    )
    cfg = replace(base, organicas=org)
    monkeypatch.setattr("apps.flujo.servicios._cfg", lambda version: cfg)
    return cfg
