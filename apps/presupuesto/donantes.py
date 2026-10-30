"""Donantes y donaciones previstas, y datos del resultado (plan de financiación, deuda)."""

from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.auditoria.servicios import Contexto, registrar

from .dinero import CERO, redondear
from .models import Donacion, Donante, Linea, TipoDonacion, TipoPersona, VersionPresupuesto
from .nif import validar_nif
from .servicios import exigir_borrador, exigir_tesorero

CAPITULOS_CON_DONANTES = ("I.2", "I.4", "I.5", "I.7")


@transaction.atomic
def crear_donante(
    contexto: Contexto,
    *,
    nombre: str,
    nif: str,
    tipo_persona: str = TipoPersona.FISICA,
    contratista_publico: bool = False,
    es_demo: bool = False,
) -> Donante:
    exigir_tesorero(contexto)
    if tipo_persona not in TipoPersona.values:
        raise ValidationError("Tipo de persona desconocido.")
    if not nombre.strip():
        raise ValidationError("Falta el nombre.")
    nif_ok = validar_nif(nif, tipo_persona)
    if Donante.objects.filter(nif=nif_ok, es_demo=es_demo).exists():
        raise ValidationError("Ya existe un donante con ese NIF.")
    donante = Donante.objects.create(
        nombre=nombre.strip(),
        nif=nif_ok,
        tipo_persona=tipo_persona,
        contratista_publico=contratista_publico,
        es_demo=es_demo,
    )
    registrar(
        contexto,
        accion="donante.crear",
        entidad="Donante",
        entidad_id=donante.pk,
        # La auditoría no se puede borrar: no guarda nombre ni NIF (derecho de supresión, RGPD).
        despues={"tipo_persona": tipo_persona},
        es_demo=es_demo,
    )
    return donante


@transaction.atomic
def dar_de_baja_donante(contexto: Contexto, donante: Donante, motivo: str) -> None:
    exigir_tesorero(contexto)
    if not motivo.strip():
        raise ValidationError("Para dar de baja a un donante hay que indicar el motivo.")
    if not donante.activo:
        return
    donante.activo = False
    donante.motivo_baja = motivo.strip()
    donante.save(update_fields=["activo", "motivo_baja"])
    registrar(
        contexto,
        accion="donante.baja",
        entidad="Donante",
        entidad_id=donante.pk,
        motivo=motivo,
        es_demo=donante.es_demo,
    )


@transaction.atomic
def registrar_donacion(
    contexto: Contexto,
    version: VersionPresupuesto,
    linea: Linea,
    donante: Donante,
    importe: Decimal,
    *,
    tipo: str = TipoDonacion.DINERARIA,
    finalista: bool = False,
    revocable: bool = False,
) -> Donacion:
    exigir_tesorero(contexto)
    exigir_borrador(version)
    errores = []
    if linea.version_id != version.pk or linea.anulada:
        errores.append("La línea no pertenece a esta versión o está anulada.")
    elif linea.partida.capitulo.codigo not in CAPITULOS_CON_DONANTES:
        errores.append(
            "Solo se registran donantes en aportaciones de cargos (I.2) y donaciones (I.4)."
        )
    if not donante.activo:
        errores.append("El donante está de baja.")
    if tipo not in TipoDonacion.values:
        errores.append("Tipo de donación desconocido.")
    importe = redondear(importe)
    if importe <= 0:
        errores.append("El importe debe ser mayor que cero.")
    if errores:
        raise ValidationError(errores)
    donacion = Donacion.objects.create(
        version=version,
        linea=linea,
        donante=donante,
        importe=importe,
        tipo=tipo,
        finalista=finalista,
        revocable=revocable,
        es_demo=version.es_demo,
    )
    registrar(
        contexto,
        accion="donacion.crear",
        entidad="Donacion",
        entidad_id=donacion.pk,
        despues={"linea": linea.codigo, "donante_id": donante.pk, "importe": str(importe)},
        es_demo=version.es_demo,
    )
    return donacion


@transaction.atomic
def anular_donacion(contexto: Contexto, donacion: Donacion, motivo: str) -> None:
    exigir_tesorero(contexto)
    exigir_borrador(donacion.version)
    if not motivo.strip():
        raise ValidationError("Para anular una donación hay que indicar el motivo.")
    if donacion.anulada:
        return
    donacion.anulada = True
    donacion.motivo_anulacion = motivo.strip()
    donacion.save()
    registrar(
        contexto,
        accion="donacion.anular",
        entidad="Donacion",
        entidad_id=donacion.pk,
        motivo=motivo,
        es_demo=donacion.version.es_demo,
    )


def acumulado_anual(version: VersionPresupuesto) -> dict[Donante, Decimal]:
    """Total previsto por donante en la versión (donaciones no anuladas), de mayor a menor."""
    total: dict[Donante, Decimal] = defaultdict(lambda: CERO)
    for d in Donacion.objects.filter(version=version, anulada=False).select_related("donante"):
        total[d.donante] += d.importe
    return dict(sorted(total.items(), key=lambda kv: (-kv[1], kv[0].nombre)))


@transaction.atomic
def guardar_resultado(
    contexto: Contexto,
    version: VersionPresupuesto,
    *,
    explicacion: str,
    plan_financiacion: str,
    endeudamiento: Decimal,
) -> None:
    """Explicación del resultado, plan de financiación y deuda prevista (V-006 y L-005)."""
    exigir_tesorero(contexto)
    exigir_borrador(version)
    endeudamiento = redondear(endeudamiento)
    if endeudamiento < 0:
        raise ValidationError("El endeudamiento previsto no puede ser negativo.")
    antes = {
        "explicacion": version.explicacion_resultado,
        "plan": version.plan_financiacion,
        "endeudamiento": str(version.endeudamiento_previsto),
    }
    version.explicacion_resultado = explicacion.strip()
    version.plan_financiacion = plan_financiacion.strip()
    version.endeudamiento_previsto = endeudamiento
    version.save(
        update_fields=["explicacion_resultado", "plan_financiacion", "endeudamiento_previsto"]
    )
    registrar(
        contexto,
        accion="version.guardar_resultado",
        entidad="VersionPresupuesto",
        entidad_id=version.pk,
        antes=antes,
        despues={
            "explicacion": version.explicacion_resultado,
            "plan": version.plan_financiacion,
            "endeudamiento": str(endeudamiento),
        },
        es_demo=version.es_demo,
    )
