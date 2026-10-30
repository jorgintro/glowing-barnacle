"""Datos de demostración. TODO es ficticio y está marcado con ``es_demo``.

Estos datos nunca se mezclan con los reales: se crean y se borran por completo con los comandos
``cargar_demo`` y ``borrar_demo``. Las cifras, los nombres y las resoluciones que aparecen aquí
son inventados para probar el sistema; no representan a ninguna organización real.

Casos que cubre (los que dependen de reglas aún no construidas llegan con su fase):
* Ingresos de los 5 capítulos y gastos de los 8 capítulos.
* Una versión en cada estado del flujo.
* Un ejercicio con campaña electoral y otros sin ella.
* Un borrador con defectos deliberados para demostrar los bloqueos V-001…V-007.
"""

import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone

from apps.auditoria.servicios import Contexto, registrar
from apps.flujo import servicios as flujo
from apps.flujo.models import (
    Convocatoria,
    Ratificacion,
    TransicionEstado,
    Votacion,
    Voto,
    VotoNominal,
)
from apps.organizacion.models import Cargo, Persona
from apps.usuarios.models import AsignacionRol, Usuario
from apps.usuarios.roles import Rol

from .dinero import redondear, repartir_proporcional, repartir_uniforme
from .models import (
    Comentario,
    CuentaPGC,
    Donacion,
    Donante,
    Ejercicio,
    Hipotesis,
    ImporteMensual,
    Linea,
    Partida,
    TipoOrigen,
    VersionPresupuesto,
)
from .nif import validar_nif

AVISO = "DATOS FICTICIOS DE DEMOSTRACIÓN"
FIRMA = " · DEMO"


@dataclass(frozen=True)
class LineaDemo:
    partida: str
    denominacion: str
    importe: str
    confianza: str
    hipotesis: str
    fuente: str
    responsable: str
    pesos: tuple[int, ...] | None = None
    tipo: str = "RECURRENTE"
    dimension: str | None = None


_TRIM = (0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1)
_ENERO = (1,) + (0,) * 11
_NOV = (0,) * 10 + (1, 0)


def _lineas_base() -> list[LineaDemo]:
    ing = "Estimación ficticia de demostración"
    return [
        LineaDemo(
            "I.1.1",
            "Cuotas de afiliados",
            "8640",
            "ALTA",
            "120 afiliados ficticios × 6,00 € al mes × 12 meses, con impagos ya descontados.",
            "Censo ficticio de afiliados",
            "Tesorería",
        ),
        LineaDemo(
            "I.2.1",
            "Aportaciones de cargos públicos",
            "3600",
            "MEDIA",
            "3 cargos ficticios × 100,00 € al mes × 12 meses.",
            "Reglamento interno ficticio",
            "Tesorería",
        ),
        LineaDemo(
            "I.3.1",
            "Subvención por representación municipal",
            "7200",
            "MEDIA",
            "Importe mensual ficticio de 600,00 € durante todo el año.",
            "Resolución ficticia DEMO-001",
            "Tesorería",
        ),
        LineaDemo(
            "I.3.2",
            "Asignación al grupo municipal",
            "18000",
            "MEDIA",
            "1.500,00 € al mes ficticios, destinados solo al grupo municipal.",
            "Acuerdo plenario ficticio DEMO-002",
            "Grupo municipal",
        ),
        LineaDemo(
            "I.4.1",
            "Donaciones dinerarias",
            "2400",
            "BAJA",
            "Media del histórico ficticio de los tres últimos años.",
            ing,
            "Tesorería",
        ),
        LineaDemo(
            "I.4.2",
            "Donaciones en especie (cartelería)",
            "300",
            "BAJA",
            "Valoración ficticia de la cartelería cedida.",
            ing,
            "Comunicación",
        ),
        LineaDemo(
            "I.5.1",
            "Venta de merchandising",
            "900",
            "MEDIA",
            "Ventas ficticias en dos actos del año y en Navidad.",
            ing,
            "Comunicación",
            pesos=(0, 0, 2, 0, 0, 3, 0, 0, 0, 0, 2, 2),
        ),
        LineaDemo(
            "I.5.2",
            "Rendimientos financieros",
            "40",
            "MEDIA",
            "Intereses ficticios de la cuenta corriente.",
            ing,
            "Tesorería",
        ),
        LineaDemo(
            "G.1.1",
            "Retribución del personal administrativo",
            "18000",
            "",
            "Una persona a jornada completa, 1.500,00 € brutos al mes (cifra ficticia).",
            "Contrato ficticio DEMO-C1",
            "Secretaría",
        ),
        LineaDemo(
            "G.1.2",
            "Cotización a cargo del partido",
            "5400",
            "",
            "Importe ficticio calculado sobre la retribución anterior.",
            "Cálculo ficticio de la gestoría",
            "Secretaría",
        ),
        LineaDemo(
            "G.2.1",
            "Alquiler de la sede",
            "4800",
            "",
            "400,00 € al mes según el contrato ficticio.",
            "Contrato ficticio DEMO-C2",
            "Secretaría",
        ),
        LineaDemo(
            "G.2.2",
            "Suministros de la sede",
            "1200",
            "",
            "Media mensual ficticia de luz, agua e internet.",
            "Facturas ficticias",
            "Secretaría",
        ),
        LineaDemo(
            "G.2.3",
            "Asesoría y gestoría",
            "1800",
            "",
            "Cuatro pagos trimestrales iguales.",
            "Presupuesto ficticio de gestoría",
            "Tesorería",
            pesos=_TRIM,
        ),
        LineaDemo(
            "G.2.4",
            "Seguro de la sede",
            "360",
            "",
            "Prima anual ficticia pagada en enero.",
            "Póliza ficticia",
            "Secretaría",
            pesos=_ENERO,
        ),
        LineaDemo(
            "G.2.5",
            "Material y mantenimiento",
            "600",
            "",
            "Gasto medio mensual ficticio.",
            "Histórico ficticio",
            "Secretaría",
        ),
        LineaDemo(
            "G.2.6",
            "Tecnologías de la información",
            "480",
            "",
            "Licencias y alojamiento ficticios.",
            "Facturas ficticias",
            "Comunicación",
        ),
        LineaDemo(
            "G.3.1",
            "Junta General ordinaria",
            "500",
            "",
            "Alquiler de sala y convocatoria para la Junta de noviembre.",
            "Presupuesto ficticio de sala",
            "Secretaría",
            pesos=_NOV,
        ),
        LineaDemo(
            "G.3.2",
            "Reuniones de la Comisión Permanente",
            "300",
            "",
            "Gastos menores de funcionamiento.",
            "Histórico ficticio",
            "Secretaría",
        ),
        LineaDemo(
            "G.3.3",
            "Formación",
            "600",
            "",
            "Dos jornadas formativas ficticias.",
            "Programa ficticio",
            "Formación",
            pesos=_TRIM,
        ),
        LineaDemo(
            "G.3.4",
            "Actos y jornadas",
            "1500",
            "",
            "Tres actos públicos ficticios.",
            "Plan de actividades ficticio",
            "Actividades",
            pesos=(0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0),
        ),
        LineaDemo(
            "G.3.5",
            "Desplazamientos",
            "400",
            "",
            "Gasto medio mensual ficticio.",
            "Histórico ficticio",
            "Actividades",
        ),
        LineaDemo(
            "G.4.1",
            "Web y redes sociales",
            "720",
            "",
            "60,00 € al mes ficticios.",
            "Contrato ficticio",
            "Comunicación",
        ),
        LineaDemo(
            "G.4.2",
            "Imprenta y cartelería",
            "900",
            "",
            "Cartelería ficticia para los actos.",
            "Presupuesto ficticio de imprenta",
            "Comunicación",
            pesos=(0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0),
        ),
        LineaDemo(
            "G.4.3",
            "Publicidad",
            "600",
            "",
            "Campañas ficticias en redes.",
            "Plan de comunicación ficticio",
            "Comunicación",
        ),
        LineaDemo(
            "G.4.4",
            "Material divulgativo",
            "500",
            "",
            "Folletos ficticios.",
            "Presupuesto ficticio de imprenta",
            "Comunicación",
            pesos=_TRIM,
        ),
        LineaDemo(
            "G.5.1",
            "Comisiones bancarias",
            "180",
            "",
            "15,00 € al mes ficticios.",
            "Condiciones ficticias del banco",
            "Tesorería",
        ),
        LineaDemo(
            "G.6.1",
            "Amortización del inmovilizado",
            "400",
            "",
            "Cuota anual ficticia del equipamiento de la sede.",
            "Inventario ficticio",
            "Tesorería",
            pesos=_ENERO,
        ),
        LineaDemo(
            "G.8.1",
            "Reserva de contingencia",
            "1000",
            "",
            "Reserva prudente ficticia para imprevistos.",
            "Criterio de prudencia",
            "Tesorería",
        ),
    ]


def _lineas_campana() -> list[LineaDemo]:
    ext = "EXTRAORDINARIO"
    return [
        LineaDemo(
            "I.3.3",
            "Subvención electoral prevista",
            "9000",
            "BAJA",
            "Importe ficticio supeditado al resultado de la elección.",
            "Estimación ficticia",
            "Tesorería",
            pesos=(0,) * 8 + (0, 0, 0, 1),
            tipo="CONDICIONADO",
            dimension="CAMPANA",
        ),
        LineaDemo(
            "I.4.1",
            "Donaciones para la campaña",
            "3200",
            "BAJA",
            "Campaña de captación ficticia entre simpatizantes.",
            "Estimación ficticia",
            "Tesorería",
            pesos=(0,) * 6 + (1, 1, 1, 1, 0, 0),
            tipo=ext,
            dimension="CAMPANA",
        ),
        LineaDemo(
            "G.7.1",
            "Cartelería y propaganda electoral",
            "6000",
            "",
            "Cartelería y papeletas ficticias.",
            "Presupuesto ficticio de imprenta",
            "Campaña",
            pesos=(0,) * 8 + (1, 1, 0, 0),
            tipo=ext,
        ),
        LineaDemo(
            "G.7.1",
            "Actos de campaña",
            "2500",
            "",
            "Cuatro actos ficticios.",
            "Plan de campaña ficticio",
            "Campaña",
            pesos=(0,) * 8 + (1, 1, 0, 0),
            tipo=ext,
        ),
        LineaDemo(
            "G.7.1",
            "Buzoneo",
            "3500",
            "",
            "Reparto ficticio a domicilio.",
            "Presupuesto ficticio de reparto",
            "Campaña",
            pesos=(0,) * 8 + (1, 1, 0, 0),
            tipo=ext,
        ),
    ]


_CACHE_PARTIDAS: dict[str, tuple[Partida, CuentaPGC | None]] = {}
_DONANTES: dict[str, Donante] = {}

# Quién aporta a cada línea de ingresos (claves de _crear_donantes). Todos son ficticios.
_DONANTES_POR_PARTIDA = {
    "I.2.1": ("C1", "C2", "C3"),
    "I.4.1": ("D1", "D2", "D3", "D4"),
    "I.4.2": ("D1",),
}
_DONANTES_CAMPANA = ("D5", "D6", "D7", "D8")


def _crear_donantes() -> None:
    """Personas ficticias (NIF de prueba con letra de control correcta, nada real)."""
    letras = "TRWAGMYFPDXBNJZSQVHLCKE"
    claves = [f"C{i}" for i in range(1, 4)] + [f"D{i}" for i in range(1, 9)]
    for n, clave in enumerate(claves, start=1):
        nombre = ("Cargo" if clave[0] == "C" else "Donante") + f" ficticio {clave}"
        nif = validar_nif(f"{n:08d}{letras[n % 23]}", "FISICA")
        _DONANTES[clave] = Donante.objects.create(nombre=nombre, nif=nif, es_demo=True)
    _DONANTES["CT"] = Donante.objects.create(
        nombre="Contratista ficticio CT",
        nif=validar_nif(f"{12:08d}{letras[12 % 23]}", "FISICA"),
        contratista_publico=True,
        es_demo=True,
    )
    _DONANTES["EMP"] = Donante.objects.create(
        nombre="Empresa ficticia S. L.", nif="B00000011", tipo_persona="JURIDICA", es_demo=True
    )


def _partida_y_cuenta(codigo: str) -> tuple[Partida, CuentaPGC | None]:
    """Partida y su primera cuenta; se memoriza durante la carga para no repetir consultas."""
    if codigo not in _CACHE_PARTIDAS:
        partida = Partida.objects.get(codigo=codigo)
        _CACHE_PARTIDAS[codigo] = (partida, partida.cuentas.order_by("codigo").first())
    return _CACHE_PARTIDAS[codigo]


class _Constructor:
    """Crea líneas directamente (sin pasar por los servicios) para sembrar datos."""

    def __init__(self, version: VersionPresupuesto) -> None:
        self.version = version
        self._contador: dict[str, int] = {}

    def anadir(
        self,
        spec: LineaDemo,
        *,
        factor: Decimal = Decimal("1"),
        con_anterior: bool = False,
        donantes: tuple[str, ...] | None = None,
        **forzar: object,
    ) -> Linea:
        partida, cuenta = _partida_y_cuenta(spec.partida)
        if spec.partida.startswith("I.5."):
            forzar.setdefault("operaciones_altas", Decimal("0.00"))
        self._contador[spec.partida] = self._contador.get(spec.partida, 0) + 1
        importe = redondear(Decimal(spec.importe) * factor)
        linea = Linea.objects.create(
            version=self.version,
            partida=partida,
            codigo=f"{spec.partida}.{self._contador[spec.partida]:02d}",
            denominacion=spec.denominacion + FIRMA,
            cuenta_pgc=cuenta,
            importe_anual=importe,
            tipo=spec.tipo,
            dimension=spec.dimension or partida.dimension_por_defecto,
            importe_ejercicio_anterior=redondear(importe / factor) if con_anterior else None,
            responsable=spec.responsable,
            **forzar,
        )
        cuotas = (
            repartir_proporcional(importe, list(spec.pesos))
            if spec.pesos
            else repartir_uniforme(importe)
        )
        ImporteMensual.objects.bulk_create(
            ImporteMensual(linea=linea, mes=m, importe=c) for m, c in enumerate(cuotas, start=1)
        )
        Hipotesis.objects.create(
            linea=linea, texto=spec.hipotesis, fuente=spec.fuente, confianza=spec.confianza
        )
        if donantes is None:
            donantes = _DONANTES_POR_PARTIDA.get(spec.partida, ())
            if spec.dimension == "CAMPANA" and spec.partida == "I.4.1":
                donantes = _DONANTES_CAMPANA
        if donantes:
            repartos = repartir_proporcional(importe, [1] * len(donantes))
            for clave, parte in zip(donantes, repartos, strict=True):
                Donacion.objects.create(
                    version=self.version,
                    linea=linea,
                    donante=_DONANTES[clave],
                    importe=parte,
                    es_demo=True,
                )
        return linea


def _explicar_resultado(version: VersionPresupuesto) -> None:
    VersionPresupuesto.objects.filter(pk=version.pk).update(
        explicacion_resultado="Superávit ficticio de demostración: los ingresos cubren los gastos."
    )
    version.refresh_from_db()


def _ejercicio(anio: int, nombre: str, campana: bool, autor: Usuario | None) -> Ejercicio:
    return Ejercicio.objects.create(
        anio=anio,
        nombre=f"{nombre} · {AVISO}",
        hay_proceso_electoral=campana,
        creado_por=autor,
        es_demo=True,
    )


def _version(
    ej: Ejercicio,
    numero: int,
    motivo: str,
    autor: Usuario | None,
    origen: VersionPresupuesto | None = None,
    tipo_origen: str = TipoOrigen.NUEVA,
) -> VersionPresupuesto:
    return VersionPresupuesto.objects.create(
        ejercicio=ej,
        numero=numero,
        motivo=motivo,
        autor=autor,
        version_origen=origen,
        tipo_origen=tipo_origen,
        es_demo=True,
    )


def _rellenar(
    version: VersionPresupuesto, *, campana: bool, factor: Decimal, anterior: bool
) -> _Constructor:
    c = _Constructor(version)
    for spec in _lineas_base():
        c.anadir(spec, factor=factor, con_anterior=anterior)
    if campana:
        for spec in _lineas_campana():
            c.anadir(spec, factor=factor, con_anterior=False)
    _explicar_resultado(version)
    return c


def _casos_incumplidos(version: VersionPresupuesto) -> None:
    """Defectos deliberados. Cada comentario indica la regla que debe bloquearlo (Fase 3)."""
    c = _Constructor(version)
    ok = _lineas_base()
    for spec in ok[:8]:  # ingresos correctos, pero insuficientes para los gastos (V-006)
        c.anadir(spec)
    gastos = {s.partida: s for s in ok}

    # V-001: la suma de los meses no coincide con el importe anual.
    linea = c.anadir(gastos["G.2.1"])
    mes = ImporteMensual.objects.get(linea=linea, mes=12)
    ImporteMensual.objects.filter(pk=mes.pk).update(importe=mes.importe - Decimal("100.00"))

    # V-003: línea sin cuenta del PGC.
    sin_cuenta = c.anadir(gastos["G.2.2"])
    Linea.objects.filter(pk=sin_cuenta.pk).update(cuenta_pgc=None)
    # V-003: cuenta que no corresponde a la partida (720 = cuotas, en un gasto de personal).
    mala = c.anadir(gastos["G.1.1"])
    Linea.objects.filter(pk=mala.pk).update(cuenta_pgc=CuentaPGC.objects.get(codigo="720"))

    # V-004: línea sin hipótesis y línea sin responsable.
    sin_hip = c.anadir(gastos["G.2.3"])
    Hipotesis.objects.filter(linea=sin_hip).update(texto="", fuente="")
    sin_resp = c.anadir(gastos["G.2.6"])
    Linea.objects.filter(pk=sin_resp.pk).update(responsable="")

    # V-005: importe negativo marcado como ajuste pero sin justificación.
    ajuste = c.anadir(gastos["G.5.1"], es_ajuste=True, justificacion_ajuste="")
    Linea.objects.filter(pk=ajuste.pk).update(importe_anual=Decimal("-180.00"))
    ImporteMensual.objects.filter(linea=ajuste).update(importe=Decimal("-15.00"))

    # V-007: variación enorme respecto al ejercicio anterior, sin justificación.
    var = c.anadir(gastos["G.4.3"])
    Linea.objects.filter(pk=var.pk).update(importe_ejercicio_anterior=Decimal("100.00"))

    # L-001: un donante supera el límite, una persona jurídica dona y hay importe sin identificar.
    c.anadir(
        LineaDemo(
            "I.4.1",
            "Donación extraordinaria de un único donante",
            "1200",
            "BAJA",
            "Donación ficticia que, sumada a las demás del mismo donante, supera el límite.",
            "Estimación ficticia",
            "Tesorería",
        ),
        donantes=("D1",),
    )
    c.anadir(
        LineaDemo(
            "I.4.1",
            "Donación de una empresa",
            "500",
            "BAJA",
            "Donación ficticia de una persona jurídica.",
            "Estimación ficticia",
            "Tesorería",
        ),
        donantes=("EMP",),
    )
    c.anadir(
        LineaDemo(
            "I.4.2",
            "Donaciones anónimas en especie",
            "250",
            "BAJA",
            "Importe ficticio sin donante identificado.",
            "Estimación ficticia",
            "Tesorería",
        ),
        donantes=(),
    )
    # L-002: ingreso de una fuente prohibida (en la configuración ficticia de demostración).
    c.anadir(
        LineaDemo(
            "I.5.3",
            "Ingreso de origen prohibido (ficticio)",
            "500",
            "BAJA",
            "Ingreso ficticio cuyo origen figura entre las fuentes prohibidas.",
            "Estimación ficticia",
            "Tesorería",
        ),
        origen_ingreso="ORIGEN_PROHIBIDO_DEMO",
    )
    # L-003: un cargo supera el límite de aportaciones y hay una aportación sin identificar.
    c.anadir(
        LineaDemo(
            "I.2.1",
            "Aportación extraordinaria de un cargo",
            "1900",
            "MEDIA",
            "Aportación ficticia que, sumada a las demás del mismo cargo, supera el límite.",
            "Estimación ficticia",
            "Tesorería",
        ),
        donantes=("C1",),
    )
    c.anadir(
        LineaDemo(
            "I.2.1",
            "Aportación sin identificar de un cargo",
            "300",
            "MEDIA",
            "Importe ficticio sin identificar al aportante.",
            "Estimación ficticia",
            "Tesorería",
        ),
        donantes=(),
    )
    # L-004: el gasto de campaña, con este gasto extra, supera el límite ficticio de 15.000 €.
    c.anadir(
        LineaDemo(
            "G.7.1",
            "Gasto de campaña adicional",
            "4000",
            "",
            "Gasto ficticio adicional.",
            "Estimación ficticia",
            "Campaña",
            tipo="EXTRAORDINARIO",
        ),
    )
    # L-005: endeudamiento superior al límite ficticio de 5.000 €.
    VersionPresupuesto.objects.filter(pk=version.pk).update(
        endeudamiento_previsto=Decimal("8000.00")
    )

    _defectos_del_extracto(version, c)

    # Gastos que, junto con los anteriores, dejan un déficit sin plan de financiación (V-006).
    for partida in ("G.1.2", "G.2.4", "G.2.5", "G.3.4", "G.4.1", "G.4.2", "G.6.1", "G.8.1"):
        c.anadir(gastos[partida])
    for spec in _lineas_campana():
        c.anadir(spec)
    c.anadir(
        LineaDemo(
            "G.3.4",
            "Gira de actos sin financiación prevista",
            "10000",
            "",
            "Gasto ficticio que deja el presupuesto en déficit, sin plan de financiación.",
            "Estimación ficticia",
            "Actividades",
        )
    )


def _donar(
    version: VersionPresupuesto, linea: Linea, clave: str, importe: str, **extra: object
) -> None:
    Donacion.objects.create(
        version=version,
        linea=linea,
        donante=_DONANTES[clave],
        importe=Decimal(importe),
        es_demo=True,
        **extra,
    )


def _defectos_del_extracto(version: VersionPresupuesto, c: _Constructor) -> None:
    """Casos de las reglas L-008 a L-011 y de la excepción de inmuebles de L-001."""
    # L-008 (aviso) y excepción de L-001: donación de un inmueble, superior al umbral de aviso.
    inmueble = c.anadir(
        LineaDemo(
            "I.4.2",
            "Donación de un inmueble (ficticia)",
            "4000",
            "BAJA",
            "Valoración ficticia de un inmueble cedido.",
            "Estimación ficticia",
            "Tesorería",
        ),
        donantes=(),
    )
    _donar(version, inmueble, "D7", "4000", tipo="ESPECIE_INMUEBLE")
    # L-009: operaciones individuales altas sin identificar al transmitente.
    c.anadir(
        LineaDemo(
            "I.5.3",
            "Ventas individuales de gran importe",
            "400",
            "BAJA",
            "Ventas ficticias a compradores sin identificar.",
            "Estimación ficticia",
            "Tesorería",
        ),
        donantes=(),
        operaciones_altas=Decimal("400.00"),
    )
    # L-010: donación de una persona parte de un contrato público vigente.
    c.anadir(
        LineaDemo(
            "I.4.1",
            "Donación de un contratista público",
            "300",
            "BAJA",
            "Donación ficticia de un contratista del sector público.",
            "Estimación ficticia",
            "Tesorería",
        ),
        donantes=("CT",),
    )
    # L-011: donaciones finalista y revocable.
    mixta = c.anadir(
        LineaDemo(
            "I.4.1",
            "Donaciones finalista y revocable",
            "200",
            "BAJA",
            "Donaciones ficticias con condiciones no admitidas.",
            "Estimación ficticia",
            "Tesorería",
        ),
        donantes=(),
    )
    _donar(version, mixta, "D2", "100", finalista=True)
    _donar(version, mixta, "D3", "100", revocable=True)


def _crear_usuarios_demo() -> tuple[dict[str, str], dict[str, Usuario]]:
    """Usuarios ficticios. El Tesorero de la demo también es miembro de la CP y vota."""
    credenciales: dict[str, str] = {}
    usuarios: dict[str, Usuario] = {}
    for nombre, roles in [
        ("demo_tesorero", [Rol.TESORERO, Rol.COMISION_PERMANENTE]),
        ("demo_cp1", [Rol.COMISION_PERMANENTE]),
        ("demo_cp2", [Rol.COMISION_PERMANENTE]),
        ("demo_cp3", [Rol.COMISION_PERMANENTE]),
        ("demo_junta", [Rol.JUNTA_GENERAL]),
    ]:
        clave = secrets.token_urlsafe(12)
        u = Usuario(
            username=nombre, first_name="Demo", last_name=nombre.split("_")[1].upper(), es_demo=True
        )
        u.set_password(clave)
        u.save()
        for rol in roles:
            AsignacionRol.objects.create(usuario=u, rol=rol)
        credenciales[nombre] = clave
        usuarios[nombre] = u
    return credenciales, usuarios


def _crear_organizacion_demo(usuarios: dict[str, Usuario]) -> None:
    """Cargos y personas ficticios para los certificados (nada de esto es real)."""
    letras = "TRWAGMYFPDXBNJZSQVHLCKE"
    cargos = {
        n: Cargo.objects.create(denominacion=f"{n} (demo)", orden=i, es_demo=True)
        for i, n in enumerate(["Gerencia", "Secretaría", "Presidencia", "Vocalía"], start=1)
    }
    for usuario, nombre, apellidos, cargo, numero in [
        ("demo_tesorero", "Teodoro", "Ficticio Demo", "Gerencia", 901),
        ("demo_cp1", "Sara", "Ficticia Demo", "Secretaría", 902),
        ("demo_cp2", "Vicente", "Ficticio Demo", "Vocalía", 903),
        ("demo_cp3", "Paula", "Ficticia Demo", "Presidencia", 904),
        ("demo_junta", "Julia", "Ficticia Demo", "Secretaría", 905),
    ]:
        p = Persona.objects.create(
            nombre=nombre,
            apellidos=apellidos,
            dni=f"{numero:08d}{letras[numero % 23]}",
            usuario=usuarios[usuario],
            es_demo=True,
        )
        p.cargos.add(cargos[cargo])


def _ctx(usuarios: dict[str, Usuario], nombre: str, rol: str) -> Contexto:
    return Contexto(usuarios[nombre], rol, None)


def _recorrer_flujo(
    version: VersionPresupuesto,
    usuarios: dict[str, Usuario],
    *,
    votos: Mapping[str, str],
    cerrar: bool = True,
    convocar: str | None = None,
    ratificar: str | None = None,
    quien_ratifica: tuple[str, str] = ("demo_junta", Rol.JUNTA_GENERAL),
    acta: str = "ACTA-DEMO",
    crear_borrador: bool = True,
) -> None:
    """Lleva la versión por el flujo REAL (así la demo también prueba el flujo)."""
    hoy = timezone.localdate()
    tesorero = _ctx(usuarios, "demo_tesorero", Rol.TESORERO)
    votacion = flujo.proponer(
        tesorero, version, avisos_aceptados=["V-007", "L-008"], confirmar=True
    )
    for nombre, voto in votos.items():
        flujo.votar(_ctx(usuarios, nombre, Rol.COMISION_PERMANENTE), votacion, voto)
    if not cerrar:
        return
    cierra = _ctx(usuarios, next(iter(votos)), Rol.COMISION_PERMANENTE)
    flujo.cerrar_votacion(
        cierra, votacion, "Votación de demostración (ficticia)", crear_borrador=crear_borrador
    )
    version.refresh_from_db()
    if version.estado != "APROBADO_CP" or convocar is None:
        return
    sesion = hoy if ratificar else hoy + timedelta(days=15)
    flujo.registrar_convocatoria(
        tesorero,
        version,
        fecha_convocatoria=hoy - timedelta(days=10),
        fecha_sesion=sesion,
        referencia=convocar,
    )
    if ratificar is None:
        return
    usuario, rol = quien_ratifica
    flujo.registrar_ratificacion(
        _ctx(usuarios, usuario, rol),
        version,
        fecha_sesion=hoy,
        resultado=ratificar,
        referencia_acta=acta,
        observaciones="Sesión ficticia de demostración.",
        avisos_aceptados=["O-004"],
        crear_borrador=crear_borrador,
    )


def existe_demo() -> bool:
    return (
        Ejercicio.objects.filter(es_demo=True).exists()
        or Usuario.objects.filter(es_demo=True).exists()
    )


def cargar_demo(contexto: Contexto) -> dict[str, str]:
    """Crea los datos de demostración. Devuelve usuario → contraseña de los usuarios demo."""
    _CACHE_PARTIDAS.clear()
    _DONANTES.clear()
    try:
        with transaction.atomic():
            return _cargar_demo(contexto)
    finally:
        _CACHE_PARTIDAS.clear()
        _DONANTES.clear()


def _cargar_demo(contexto: Contexto) -> dict[str, str]:
    """Crea los datos de demostración. Devuelve usuario → contraseña de los usuarios demo."""
    if existe_demo():
        raise RuntimeError(
            "Ya hay datos de demostración cargados. Bórralos antes de volver a cargarlos."
        )
    credenciales, usuarios = _crear_usuarios_demo()
    _crear_organizacion_demo(usuarios)
    _crear_donantes()
    autor = usuarios["demo_tesorero"]
    A, C, N = Voto.A_FAVOR, Voto.EN_CONTRA, Voto.ABSTENCION
    todos_a_favor = {"demo_tesorero": A, "demo_cp1": A, "demo_cp2": A, "demo_cp3": A}
    mayoria = {"demo_tesorero": A, "demo_cp1": A, "demo_cp2": A, "demo_cp3": N}

    # 2027 · con campaña: v1 rechazada por la Junta, v2 ratificada, v3 modificación.
    e2027 = _ejercicio(2027, "Ejercicio de demostración con campaña", True, autor)
    v1 = _version(e2027, 1, "Primera propuesta (rechazada por la Junta en la demostración)", autor)
    _rellenar(v1, campana=True, factor=Decimal("0.90"), anterior=False)
    _recorrer_flujo(
        v1,
        usuarios,
        votos=todos_a_favor,
        convocar="CONV-DEMO-01",
        ratificar="RECHAZADO",
        acta="ACTA-DEMO-01",
        crear_borrador=False,
    )
    v2 = _version(e2027, 2, "Versión corregida tras el rechazo", autor, v1, TipoOrigen.TRAS_RECHAZO)
    _rellenar(v2, campana=True, factor=Decimal("1.00"), anterior=False)
    _recorrer_flujo(
        v2,
        usuarios,
        votos=mayoria,
        convocar="CONV-DEMO-02",
        ratificar="RATIFICADO",
        quien_ratifica=("demo_tesorero", Rol.TESORERO),
        acta="ACTA-DEMO-02",
    )
    v3 = _version(
        e2027, 3, "Modificación: reforma ficticia de la sede", autor, v2, TipoOrigen.MODIFICACION
    )
    c3 = _rellenar(v3, campana=True, factor=Decimal("1.00"), anterior=False)
    c3.anadir(
        LineaDemo(
            "G.2.5",
            "Reforma de la sede",
            "400",
            "",
            "Obra menor ficticia, extraordinaria (no supera el umbral ficticio de la Junta).",
            "Presupuesto ficticio de obra",
            "Secretaría",
            tipo="EXTRAORDINARIO",
        )
    )
    _recorrer_flujo(v3, usuarios, votos=mayoria)

    # Ejercicios sin campaña, cada uno en un punto del flujo.
    e2028 = _ejercicio(2028, "Ejercicio de demostración sin campaña (Borrador)", False, autor)
    v = _version(e2028, 1, "Borrador de trabajo del Tesorero", autor)
    _rellenar(v, campana=False, factor=Decimal("1.00"), anterior=False)

    e2029 = _ejercicio(2029, "Ejercicio de demostración sin campaña (Propuesto)", False, autor)
    v2029 = _version(e2029, 1, "Propuesto a la Comisión Permanente (votación abierta)", autor)
    _rellenar(v2029, campana=False, factor=Decimal("1.02"), anterior=True)
    _recorrer_flujo(v2029, usuarios, votos={"demo_cp1": A}, cerrar=False)
    flujo.comentar(
        _ctx(usuarios, "demo_cp2", Rol.COMISION_PERMANENTE),
        v2029,
        "Comentario ficticio de demostración: ¿se puede detallar mejor la partida de actos?",
    )

    e2030 = _ejercicio(2030, "Ejercicio de demostración sin campaña (Aprobado)", False, autor)
    v2030 = _version(e2030, 1, "Aprobado por la Comisión Permanente", autor)
    _rellenar(v2030, campana=False, factor=Decimal("1.04"), anterior=True)
    _recorrer_flujo(
        v2030,
        usuarios,
        votos={"demo_tesorero": A, "demo_cp1": A, "demo_cp2": A, "demo_cp3": C},
        convocar="CONV-DEMO-03",
    )

    # 2031 · con campaña y defectos deliberados.
    e2031 = _ejercicio(2031, "Casos que incumplen reglas", True, autor)
    v = _version(e2031, 1, "Borrador con errores deliberados para probar los bloqueos", autor)
    _casos_incumplidos(v)

    # 2032 · rechazada por la Comisión Permanente (y nuevo borrador automático).
    e2032 = _ejercicio(2032, "Ejercicio de demostración rechazado por la CP", False, autor)
    v = _version(e2032, 1, "Propuesta que la Comisión Permanente rechaza en la demostración", autor)
    _rellenar(v, campana=False, factor=Decimal("1.00"), anterior=False)
    _recorrer_flujo(
        v, usuarios, votos={"demo_tesorero": A, "demo_cp1": C, "demo_cp2": C, "demo_cp3": C}
    )

    registrar(
        contexto,
        accion="demo.cargar",
        entidad="Demo",
        es_demo=True,
        despues={
            "ejercicios": Ejercicio.objects.filter(es_demo=True).count(),
            "versiones": VersionPresupuesto.objects.filter(es_demo=True).count(),
            "usuarios": sorted(credenciales),
        },
    )
    return credenciales


@transaction.atomic
def borrar_demo(contexto: Contexto) -> dict[str, int]:
    """Borra SOLO lo marcado como demostración. Lo real no se toca."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('presupuesto.modo_demo', 'on', true)")
        cursor.execute("DELETE FROM auditoria_registroauditoria WHERE es_demo")
        auditoria = cursor.rowcount

    # Se borra por listas de identificadores (no por subconsultas con JOIN): así el plan de
    # PostgreSQL no depende de estadísticas y el borrado es rápido aunque haya muchas filas.
    versiones = VersionPresupuesto.objects.filter(es_demo=True)
    ids_lineas = list(Linea.objects.filter(version__es_demo=True).values_list("pk", flat=True))
    cuentas = {
        "votos": VotoNominal.objects.filter(es_demo=True).delete()[0],
        "votaciones": Votacion.objects.filter(es_demo=True).delete()[0],
        "ratificaciones": Ratificacion.objects.filter(es_demo=True).delete()[0],
        "convocatorias": Convocatoria.objects.filter(es_demo=True).delete()[0],
        "transiciones": TransicionEstado.objects.filter(es_demo=True).delete()[0],
        "importes_mensuales": ImporteMensual.objects.filter(linea_id__in=ids_lineas).delete()[0],
        "donaciones": Donacion.objects.filter(version__es_demo=True).delete()[0],
        "hipotesis": Hipotesis.objects.filter(linea_id__in=ids_lineas).delete()[0],
        "comentarios": Comentario.objects.filter(es_demo=True).delete()[0],
        "lineas": Linea.objects.filter(pk__in=ids_lineas).delete()[0],
    }
    cuentas["donantes"] = Donante.objects.filter(es_demo=True).delete()[0]
    # Las versiones derivadas se borran antes que su origen (no se puede «desenlazar» una versión
    # sellada: el disparador lo impediría).
    borradas = 0
    while versiones.exists():
        hojas = versiones.filter(derivadas__isnull=True)
        if not hojas.exists():  # defensa ante un ciclo imposible
            break
        borradas += hojas.delete()[0]
    cuentas["versiones"] = borradas
    cuentas["ejercicios"] = Ejercicio.objects.filter(es_demo=True).delete()[0]
    cuentas["personas"] = Persona.objects.filter(es_demo=True).delete()[0]
    cuentas["cargos"] = Cargo.objects.filter(es_demo=True).delete()[0]
    demo = Usuario.objects.filter(es_demo=True)
    AsignacionRol.objects.filter(usuario__in=demo).delete()
    cuentas["usuarios"] = demo.delete()[0]
    cuentas["auditoria"] = auditoria

    # Constancia (no demo) de que se borró, para que el histórico real no tenga huecos mudos.
    registrar(contexto, accion="demo.borrar", entidad="Demo", despues=dict(cuentas))
    return cuentas
