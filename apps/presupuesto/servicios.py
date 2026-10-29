"""Operaciones del Tesorero sobre el borrador. Cada una comprueba permisos, valida y audita."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.servicios import Contexto, registrar
from apps.usuarios.roles import Rol

from .dinero import CERO, redondear, repartir_uniforme
from .errores import VersionNoEditable
from .estados import EstadoVersion
from .models import (
    CuentaPGC,
    Ejercicio,
    Hipotesis,
    ImporteMensual,
    Linea,
    Partida,
    VersionPresupuesto,
)


def exigir_tesorero(contexto: Contexto) -> None:
    if contexto.usuario is None or contexto.rol_activo != Rol.TESORERO:
        raise PermissionDenied("Solo el Tesorero puede elaborar el presupuesto.")


def exigir_borrador(version: VersionPresupuesto) -> None:
    if not version.editable:
        raise VersionNoEditable(
            f"La versión {version} es de solo lectura (estado: {version.get_estado_display()}). "
            "Los cambios exigen una modificación presupuestaria."
        )


@transaction.atomic
def crear_ejercicio(
    contexto: Contexto,
    *,
    anio: int,
    nombre: str = "",
    hay_proceso_electoral: bool = False,
    es_demo: bool = False,
) -> tuple[Ejercicio, VersionPresupuesto]:
    exigir_tesorero(contexto)
    if not 2000 <= anio <= 2100:
        raise ValidationError("El año del ejercicio no es válido.")
    if Ejercicio.objects.filter(anio=anio, es_demo=es_demo).exists():
        raise ValidationError(f"Ya existe un ejercicio {anio}.")
    ejercicio = Ejercicio.objects.create(
        anio=anio,
        nombre=nombre,
        hay_proceso_electoral=hay_proceso_electoral,
        creado_por=contexto.usuario,
        es_demo=es_demo,
    )
    version = VersionPresupuesto.objects.create(
        ejercicio=ejercicio,
        numero=1,
        estado=EstadoVersion.BORRADOR,
        autor=contexto.usuario,
        motivo="Primera versión del ejercicio",
        es_demo=es_demo,
    )
    registrar(
        contexto,
        accion="ejercicio.crear",
        entidad="Ejercicio",
        entidad_id=ejercicio.pk,
        despues={"anio": anio, "proceso_electoral": hay_proceso_electoral, "version": 1},
        es_demo=es_demo,
    )
    return ejercicio, version


def _siguiente_codigo(version: VersionPresupuesto, partida: Partida) -> str:
    existentes = Linea.objects.filter(version=version, partida=partida).values_list(
        "codigo", flat=True
    )
    ultimo = 0
    for codigo in existentes:
        sufijo = codigo.rsplit(".", 1)[-1]
        if sufijo.isdigit():
            ultimo = max(ultimo, int(sufijo))
    return f"{partida.codigo}.{ultimo + 1:02d}"


@dataclass(frozen=True)
class DatosHipotesis:
    texto: str
    fuente: str
    confianza: str = ""


def _instantanea(linea: Linea) -> dict[str, Any]:
    h = getattr(linea, "hipotesis", None) if linea.pk else None
    return {
        "codigo": linea.codigo,
        "partida": linea.partida.codigo,
        "denominacion": linea.denominacion,
        "cuenta": linea.cuenta_pgc.codigo if linea.cuenta_pgc else None,
        "importe_anual": str(linea.importe_anual),
        "mensual": [str(i.importe) for i in linea.importes_mensuales.order_by("mes")]
        if linea.pk
        else [],
        "tipo": linea.tipo,
        "dimension": linea.dimension,
        "importe_anterior": str(linea.importe_ejercicio_anterior)
        if linea.importe_ejercicio_anterior is not None
        else None,
        "responsable": linea.responsable,
        "es_ajuste": linea.es_ajuste,
        "hipotesis": {"texto": h.texto, "fuente": h.fuente, "confianza": h.confianza}
        if h
        else None,
        "anulada": linea.anulada,
    }


@transaction.atomic
def guardar_linea(
    contexto: Contexto,
    version: VersionPresupuesto,
    *,
    partida: Partida,
    denominacion: str,
    cuenta: CuentaPGC,
    importe_anual: Decimal,
    hipotesis: DatosHipotesis,
    responsable: str,
    mensual: Sequence[Decimal] | None = None,
    tipo: str = "RECURRENTE",
    dimension: str | None = None,
    importe_anterior: Decimal | None = None,
    justificacion_variacion: str = "",
    es_ajuste: bool = False,
    justificacion_ajuste: str = "",
    linea: Linea | None = None,
) -> Linea:
    """Crea o actualiza una línea con su distribución mensual y su hipótesis.

    Si ``mensual`` es ``None`` el importe se reparte por igual entre los 12 meses.
    """
    exigir_tesorero(contexto)
    exigir_borrador(version)
    if linea is not None and (linea.version_id != version.pk or linea.anulada):
        raise ValidationError("Esa línea no se puede modificar.")

    errores: list[str] = []
    importe_anual = redondear(importe_anual)
    capitulo = partida.capitulo
    if not partida.activa or not capitulo.activo:
        errores.append("La partida elegida ya no está activa.")
    if capitulo.solo_con_proceso_electoral and not version.ejercicio.hay_proceso_electoral:
        errores.append("Este capítulo solo se usa si el ejercicio tiene proceso electoral.")
    if not partida.cuentas.filter(pk=cuenta.pk).exists():
        errores.append(f"La cuenta {cuenta.codigo} no corresponde a la partida {partida.codigo}.")
    if not denominacion.strip():
        errores.append("Falta la denominación.")
    if not responsable.strip():
        errores.append("Falta el responsable.")
    if not hipotesis.texto.strip() or not hipotesis.fuente.strip():
        errores.append("La hipótesis y su fuente son obligatorias.")
    if importe_anual < 0 and not (es_ajuste and justificacion_ajuste.strip()):
        errores.append("No se admiten importes negativos salvo ajustes justificados.")
    if es_ajuste and not justificacion_ajuste.strip():
        errores.append("Un ajuste exige justificación.")
    if mensual is None:
        cuotas = repartir_uniforme(importe_anual)
    else:
        cuotas = [redondear(m) for m in mensual]
        if len(cuotas) != 12:
            errores.append("Hacen falta los 12 importes mensuales.")
        elif sum(cuotas, CERO) != importe_anual:
            errores.append(
                f"La suma de los meses ({sum(cuotas, CERO)}) no coincide con el importe anual "
                f"({importe_anual})."
            )
    if errores:
        raise ValidationError(errores)

    antes = _instantanea(linea) if linea else None
    if linea is None:
        linea = Linea(version=version, partida=partida, codigo=_siguiente_codigo(version, partida))
    elif linea.partida_id != partida.pk:
        linea.partida = partida
        linea.codigo = _siguiente_codigo(version, partida)
    linea.denominacion = denominacion.strip()
    linea.cuenta_pgc = cuenta
    linea.importe_anual = importe_anual
    linea.tipo = tipo
    linea.dimension = dimension or partida.dimension_por_defecto
    linea.importe_ejercicio_anterior = (
        redondear(importe_anterior) if importe_anterior is not None else None
    )
    linea.justificacion_variacion = justificacion_variacion
    linea.responsable = responsable.strip()
    linea.es_ajuste = es_ajuste
    linea.justificacion_ajuste = justificacion_ajuste
    linea.modificada = timezone.now()
    linea.save()

    for mes, importe in enumerate(cuotas, start=1):
        ImporteMensual.objects.update_or_create(linea=linea, mes=mes, defaults={"importe": importe})
    Hipotesis.objects.update_or_create(
        linea=linea,
        defaults={
            "texto": hipotesis.texto.strip(),
            "fuente": hipotesis.fuente.strip(),
            "confianza": hipotesis.confianza,
        },
    )
    registrar(
        contexto,
        accion="linea.crear" if antes is None else "linea.modificar",
        entidad="Linea",
        entidad_id=linea.pk,
        antes=antes,
        despues=_instantanea(linea),
        es_demo=version.es_demo,
    )
    return linea


@transaction.atomic
def anular_linea(contexto: Contexto, linea: Linea, motivo: str) -> None:
    """Las líneas no se borran: se anulan con motivo y dejan de sumar."""
    exigir_tesorero(contexto)
    exigir_borrador(linea.version)
    if not motivo.strip():
        raise ValidationError("Para anular una línea hay que indicar el motivo.")
    if linea.anulada:
        return
    antes = _instantanea(linea)
    linea.anulada = True
    linea.motivo_anulacion = motivo.strip()
    linea.anulada_por = contexto.usuario
    linea.fecha_anulacion = timezone.now()
    linea.modificada = timezone.now()
    linea.save()
    registrar(
        contexto,
        accion="linea.anular",
        entidad="Linea",
        entidad_id=linea.pk,
        antes=antes,
        despues=_instantanea(linea),
        motivo=motivo,
        es_demo=linea.version.es_demo,
    )
