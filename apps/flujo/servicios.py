"""Servicios del flujo de aprobación (CLAUDE.md §5).

Cada operación comprueba el rol, valida, deja constancia en la auditoría y, si cambia el estado,
registra la transición con su huella. La base de datos rechaza además cualquier cambio de estado
no permitido y cualquier modificación del contenido de una versión que no sea borrador.
"""

from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.auditoria.servicios import Contexto, registrar
from apps.presupuesto.calculos import resumen_version
from apps.presupuesto.configuracion import ConfiguracionVersion, cargar_configuracion
from apps.presupuesto.dinero import CERO, formatear_euros
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import (
    Comentario,
    Donacion,
    Ejercicio,
    Hipotesis,
    ImporteMensual,
    Linea,
    TipoLinea,
    TipoOrigen,
    VersionPresupuesto,
)
from apps.usuarios.models import Usuario
from apps.usuarios.roles import Rol
from apps.validaciones.motor import validar_version
from apps.validaciones.reglas_o import (
    DatosRatificacion,
    DatosVotacion,
    evaluar_votacion,
    o002,
    o003,
    o004,
)
from apps.validaciones.tipos import ResultadoValidacion

from .models import (
    Convocatoria,
    EstadoVotacion,
    Ratificacion,
    ResultadoRatificacion,
    ResultadoVotacion,
    TransicionEstado,
    Votacion,
    Voto,
    VotoNominal,
)
from .sello import calcular_hash, hash_encadenado, iso_utc, verificar_integridad

VIGENTES = (EstadoVersion.RATIFICADO_JG, EstadoVersion.MODIFICADO)
ABIERTAS = (EstadoVersion.BORRADOR, EstadoVersion.PROPUESTO, EstadoVersion.APROBADO_CP)


class IntegridadRota(Exception):
    """El contenido de una versión sellada no coincide con su huella."""


# ------------------------------------------------------------------------ utilidades


def _exigir_rol(contexto: Contexto, *roles: str) -> None:
    if contexto.usuario is None or contexto.rol_activo not in roles:
        nombres = " o ".join(Rol(r).label for r in roles)
        raise PermissionDenied(f"Esta acción corresponde a: {nombres}.")


def _cfg(version: VersionPresupuesto) -> ConfiguracionVersion:
    return cargar_configuracion(version.es_demo)


def _exigir_estado(version: VersionPresupuesto, *estados: str) -> None:
    version.refresh_from_db()
    if version.estado not in estados:
        permitido = " o ".join(EstadoVersion(e).label for e in estados)
        raise ValidationError(
            f"La versión está en estado «{version.get_estado_display()}»; se esperaba: {permitido}."
        )


def miembros_cp(es_demo: bool) -> QuerySet[Usuario]:
    """Miembros de la Comisión Permanente: usuarios activos con ese rol (los demo, con los demo)."""
    return Usuario.objects.filter(
        is_active=True,
        es_demo=es_demo,
        asignaciones__rol=Rol.COMISION_PERMANENTE,
        asignaciones__fecha_fin__isnull=True,
    ).distinct()


def _snapshot(res: ResultadoValidacion) -> dict[str, Any]:
    return {
        "reglas_ejecutadas": res.reglas_ejecutadas,
        "superadas": res.superadas(),
        "incidencias": [
            {
                "codigo": i.codigo,
                "gravedad": i.gravedad.value,
                "mensaje": i.mensaje,
                "linea": i.linea,
            }
            for i in res.incidencias
        ],
    }


def _transitar(
    contexto: Contexto,
    version: VersionPresupuesto,
    a_estado: str,
    *,
    motivo: str = "",
    validacion: dict[str, Any] | None = None,
    avisos: Iterable[str] = (),
    cambios: dict[str, Any] | None = None,
) -> TransicionEstado:
    """Cambia el estado (la base de datos valida la transición) y la anota con su huella."""
    version.refresh_from_db()
    de_estado = version.estado
    campos: dict[str, Any] = {"estado": a_estado, **(cambios or {})}
    VersionPresupuesto.objects.filter(pk=version.pk).update(**campos)
    version.refresh_from_db()
    previo = TransicionEstado.objects.filter(version=version).order_by("-id").first()
    hash_previo = previo.hash_encadenado if previo else ""
    ahora = timezone.now()
    usuario = contexto.usuario
    t = TransicionEstado.objects.create(
        version=version,
        de_estado=de_estado,
        a_estado=a_estado,
        usuario=usuario,
        rol=contexto.rol_activo,
        fecha=ahora,
        motivo=motivo,
        hash_version=version.hash,
        hash_previo=hash_previo,
        hash_encadenado=hash_encadenado(
            hash_previo=hash_previo,
            hash_version=version.hash,
            de_estado=de_estado,
            a_estado=a_estado,
            usuario_id=usuario.pk if usuario else None,
            fecha_iso=iso_utc(ahora),
            motivo=motivo,
        ),
        validacion=validacion,
        avisos_aceptados=sorted(avisos),
        es_demo=version.es_demo,
    )
    registrar(
        contexto,
        accion=f"version.{a_estado.lower()}",
        entidad="VersionPresupuesto",
        entidad_id=version.pk,
        antes={"estado": de_estado},
        despues={"estado": a_estado, "hash": version.hash},
        motivo=motivo,
        es_demo=version.es_demo,
    )
    return t


def _exigir_integridad(contexto: Contexto, version: VersionPresupuesto) -> None:
    res = verificar_integridad(version)
    if not res.ok:
        registrar(
            contexto,
            accion="version.integridad_rota",
            entidad="VersionPresupuesto",
            entidad_id=version.pk,
            despues={"problemas": res.problemas},
            es_demo=version.es_demo,
        )
        raise IntegridadRota(" ".join(res.problemas))


def vigente(ejercicio: Ejercicio) -> VersionPresupuesto | None:
    """Última versión aprobada del ejercicio (ratificada o modificación aprobada)."""
    return ejercicio.versiones.filter(estado__in=VIGENTES).order_by("-numero").first()


# ------------------------------------------------------------------------- proponer


@transaction.atomic
def proponer(
    contexto: Contexto,
    version: VersionPresupuesto,
    *,
    avisos_aceptados: Iterable[str] = (),
    confirmar: bool = False,
) -> Votacion:
    """BORRADOR → PROPUESTO: valida, sella con huella y abre la votación de la CP."""
    _exigir_rol(contexto, Rol.TESORERO)
    _exigir_estado(version, EstadoVersion.BORRADOR)
    if not confirmar:
        raise ValidationError("Debes confirmar expresamente que quieres proponer esta versión.")
    resultado = validar_version(version)
    if resultado.bloqueantes:
        raise ValidationError(
            ["No se puede proponer: hay bloqueos."]
            + [f"{i.codigo}: {i.mensaje}" for i in resultado.bloqueantes]
        )
    avisos = {i.codigo for i in resultado.avisos}
    sin_aceptar = avisos - set(avisos_aceptados)
    if sin_aceptar:
        raise ValidationError(
            "Hay avisos sin aceptar: "
            + ", ".join(sorted(sin_aceptar))
            + ". Acéptalos para dejar constancia."
        )
    sello = calcular_hash(version)
    t = _transitar(
        contexto,
        version,
        EstadoVersion.PROPUESTO,
        motivo="Propuesta a la Comisión Permanente",
        validacion=_snapshot(resultado),
        avisos=avisos,
        cambios={"hash": sello, "proponente": contexto.usuario},
    )
    votacion = Votacion.objects.create(
        version=version, abierta_por=contexto.usuario, es_demo=version.es_demo
    )
    registrar(
        contexto,
        accion="votacion.abrir",
        entidad="Votacion",
        entidad_id=votacion.pk,
        despues={"version": version.pk, "transicion": t.pk},
        es_demo=version.es_demo,
    )
    return votacion


# ------------------------------------------------------------------------- devolver


def _anular_votacion_abierta(contexto: Contexto, version: VersionPresupuesto) -> None:
    for v in Votacion.objects.filter(version=version, estado=EstadoVotacion.ABIERTA):
        v.estado = EstadoVotacion.CERRADA
        v.resultado = ResultadoVotacion.ANULADA
        v.cerrada_por = contexto.usuario
        v.cerrada_en = timezone.now()
        v.save()


@transaction.atomic
def devolver(contexto: Contexto, version: VersionPresupuesto, motivo: str) -> None:
    """PROPUESTO → BORRADOR: la Comisión Permanente devuelve la propuesta con motivos."""
    _exigir_rol(contexto, Rol.COMISION_PERMANENTE)
    _exigir_estado(version, EstadoVersion.PROPUESTO)
    if not motivo.strip():
        raise ValidationError("Para devolver la propuesta hay que indicar los motivos.")
    _exigir_integridad(contexto, version)
    _anular_votacion_abierta(contexto, version)
    _transitar(
        contexto,
        version,
        EstadoVersion.BORRADOR,
        motivo=motivo.strip(),
        cambios={"hash": "", "proponente": None},
    )


# --------------------------------------------------------------------------- votar


def _datos_votacion(votacion: Votacion, version: VersionPresupuesto) -> DatosVotacion:
    votos = list(votacion.votos.all())
    return DatosVotacion(
        miembros=miembros_cp(version.es_demo).count(),
        asistentes=len(votos),
        a_favor=sum(v.voto == Voto.A_FAVOR for v in votos),
        en_contra=sum(v.voto == Voto.EN_CONTRA for v in votos),
        abstenciones=sum(v.voto == Voto.ABSTENCION for v in votos),
        proponente=version.proponente_id,
        votantes=tuple(v.usuario_id for v in votos),
    )


def datos_votacion(votacion: Votacion) -> DatosVotacion:
    return _datos_votacion(votacion, votacion.version)


@transaction.atomic
def votar(contexto: Contexto, votacion: Votacion, voto: str) -> VotoNominal:
    """Voto nominal de un miembro. Puede cambiarlo mientras la votación siga abierta."""
    _exigir_rol(contexto, Rol.COMISION_PERMANENTE)
    votacion.refresh_from_db()
    version = votacion.version
    if votacion.estado != EstadoVotacion.ABIERTA:
        raise ValidationError("La votación está cerrada.")
    if voto not in Voto.values:
        raise ValidationError("Voto desconocido.")
    usuario = contexto.usuario
    assert usuario is not None
    if not miembros_cp(version.es_demo).filter(pk=usuario.pk).exists():
        raise PermissionDenied("No eres miembro de la Comisión Permanente de esta versión.")
    cfg = _cfg(version).organicas
    incidencia = o003(
        DatosVotacion(0, 0, 0, 0, 0, proponente=version.proponente_id, votantes=(usuario.pk,)), cfg
    )
    if incidencia:
        raise ValidationError(incidencia[0].mensaje)
    existente = VotoNominal.objects.filter(votacion=votacion, usuario=usuario).first()
    if existente is None:
        v = VotoNominal.objects.create(
            votacion=votacion, usuario=usuario, voto=voto, es_demo=version.es_demo
        )
        accion, antes = "voto.emitir", None
    else:
        antes = {"voto": existente.voto}
        existente.voto = voto
        existente.emitido_en = timezone.now()
        existente.save()
        v, accion = existente, "voto.cambiar"
    registrar(
        contexto,
        accion=accion,
        entidad="VotoNominal",
        entidad_id=v.pk,
        antes=antes,
        despues={"voto": voto, "votacion": votacion.pk},
        es_demo=version.es_demo,
    )
    return v


# ------------------------------------------------------------------ cerrar votación


def decidir_requiere_junta(
    version: VersionPresupuesto, cfg: ConfiguracionVersion
) -> tuple[bool, str]:
    """¿Una modificación debe volver a la Junta? (§5.3 de CLAUDE.md)."""
    origen = version.version_origen
    if version.tipo_origen != TipoOrigen.MODIFICACION or origen is None:
        return True, "Toda versión nueva debe ser ratificada por la Junta General."
    nuevo, antiguo = resumen_version(version), resumen_version(origen)
    d_ing = abs(nuevo.ingresos - antiguo.ingresos)
    d_gas = abs(nuevo.gastos - antiguo.gastos)
    org = cfg.organicas
    if d_ing == CERO and d_gas == CERO:
        if org.transferencias_solo_cp:
            return (
                False,
                "Transferencia entre partidas sin cambiar los totales: "
                "basta la Comisión Permanente.",
            )
        return (
            True,
            "Transferencia entre partidas: el reglamento no la deja "
            "solo en la Comisión Permanente.",
        )
    umbral = org.umbral_modificacion_junta
    if umbral is None:
        return (
            True,
            "No hay umbral de modificación configurado: vuelve a la Junta (opción prudente).",
        )
    if umbral.tipo == "IMPORTE":
        medida = max(d_ing, d_gas)
        if medida > umbral.valor:
            return (
                True,
                f"La modificación ({formatear_euros(medida)}) supera el umbral "
                f"de {formatear_euros(umbral.valor)}.",
            )
        return (
            False,
            f"La modificación ({formatear_euros(medida)}) no supera el umbral "
            f"de {formatear_euros(umbral.valor)}.",
        )
    base = max(antiguo.ingresos, antiguo.gastos)
    if base == 0:
        return True, "El presupuesto de origen es cero: vuelve a la Junta."
    pct = max(d_ing, d_gas) * 100 / base
    if pct > umbral.valor:
        return True, f"La modificación ({pct:.2f} %) supera el umbral del {umbral.valor} %."
    return False, f"La modificación ({pct:.2f} %) no supera el umbral del {umbral.valor} %."


@transaction.atomic
def cerrar_votacion(
    contexto: Contexto,
    votacion: Votacion,
    observaciones: str = "",
    *,
    crear_borrador: bool = True,
) -> Votacion:
    """Cierra la votación: con quórum y mayoría aprueba; con quórum sin mayoría, rechaza."""
    _exigir_rol(contexto, Rol.COMISION_PERMANENTE)
    votacion.refresh_from_db()
    version = votacion.version
    if votacion.estado != EstadoVotacion.ABIERTA:
        raise ValidationError("La votación ya está cerrada.")
    _exigir_estado(version, EstadoVersion.PROPUESTO)
    _exigir_integridad(contexto, version)
    cfg = _cfg(version)
    datos = _datos_votacion(votacion, version)
    evaluacion = evaluar_votacion(datos, cfg.organicas)
    if not (evaluacion.configurada and evaluacion.coherente and evaluacion.quorum):
        raise ValidationError([i.mensaje for i in evaluacion.incidencias])
    prohibido = o003(datos, cfg.organicas)
    if prohibido:
        raise ValidationError(prohibido[0].mensaje)
    aprobada = evaluacion.mayoria
    votacion.estado = EstadoVotacion.CERRADA
    votacion.resultado = ResultadoVotacion.APROBADA if aprobada else ResultadoVotacion.RECHAZADA
    votacion.cerrada_por, votacion.cerrada_en = contexto.usuario, timezone.now()
    votacion.observaciones = observaciones.strip()
    votacion.miembros, votacion.asistentes = datos.miembros, datos.asistentes
    votacion.a_favor, votacion.en_contra = datos.a_favor, datos.en_contra
    votacion.abstenciones = datos.abstenciones
    votacion.evaluacion = {
        "quorum": evaluacion.quorum,
        "mayoria": evaluacion.mayoria,
        "mensajes": [i.mensaje for i in evaluacion.incidencias],
    }
    votacion.save()
    registrar(
        contexto,
        accion="votacion.cerrar",
        entidad="Votacion",
        entidad_id=votacion.pk,
        despues={"resultado": votacion.resultado, **votacion.evaluacion},
        motivo=votacion.observaciones,
        es_demo=version.es_demo,
    )
    resumen = (
        f"Votación cerrada: {datos.a_favor} a favor, {datos.en_contra} en contra y "
        f"{datos.abstenciones} abstenciones ({datos.asistentes} de {datos.miembros} miembros)."
    )
    if aprobada:
        junta, razon = decidir_requiere_junta(version, cfg)
        _transitar(
            contexto,
            version,
            EstadoVersion.APROBADO_CP,
            motivo=resumen,
            cambios={"requiere_junta": junta},
        )
        if not junta:
            _transitar(
                contexto,
                version,
                EstadoVersion.MODIFICADO,
                motivo=f"Modificación aprobada solo por la Comisión Permanente. {razon}",
            )
    else:
        _transitar(
            contexto,
            version,
            EstadoVersion.RECHAZADO,
            motivo="Rechazada por la Comisión Permanente. " + resumen,
        )
        if crear_borrador:
            nuevo_borrador_desde(
                contexto,
                version,
                TipoOrigen.TRAS_RECHAZO,
                "Nuevo borrador tras el rechazo de la Comisión Permanente",
                _interno=True,
            )
    return votacion


# -------------------------------------------------------------------- Junta General


def _exigir_puede_ratificar(contexto: Contexto, version: VersionPresupuesto) -> None:
    permitidos = _cfg(version).organicas.ratificacion_registrada_por
    _exigir_rol(contexto, *permitidos)


@transaction.atomic
def registrar_convocatoria(
    contexto: Contexto,
    version: VersionPresupuesto,
    *,
    fecha_convocatoria: date,
    fecha_sesion: date,
    referencia: str = "",
) -> Convocatoria:
    _exigir_rol(contexto, Rol.TESORERO, Rol.JUNTA_GENERAL)
    _exigir_estado(version, EstadoVersion.APROBADO_CP)
    if not version.requiere_junta:
        raise ValidationError("Esta versión no necesita ratificación de la Junta.")
    if fecha_sesion < fecha_convocatoria:
        raise ValidationError("La sesión no puede ser anterior a la convocatoria.")
    c = Convocatoria.objects.create(
        version=version,
        fecha_convocatoria=fecha_convocatoria,
        fecha_sesion=fecha_sesion,
        referencia=referencia.strip(),
        registrada_por=contexto.usuario,
        es_demo=version.es_demo,
    )
    registrar(
        contexto,
        accion="convocatoria.registrar",
        entidad="Convocatoria",
        entidad_id=c.pk,
        despues={"version": version.pk, "fecha_sesion": str(fecha_sesion)},
        es_demo=version.es_demo,
    )
    return c


def datos_ratificacion_previos(version: VersionPresupuesto) -> tuple[date | None, date | None]:
    """(fecha de la aprobación de la CP, fecha de la última convocatoria)."""
    aprobacion = (
        TransicionEstado.objects.filter(version=version, a_estado=EstadoVersion.APROBADO_CP)
        .order_by("-id")
        .first()
    )
    conv = Convocatoria.objects.filter(version=version).order_by("-id").first()
    return (
        timezone.localtime(aprobacion.fecha).date() if aprobacion else None,
        conv.fecha_convocatoria if conv else None,
    )


@transaction.atomic
def registrar_ratificacion(
    contexto: Contexto,
    version: VersionPresupuesto,
    *,
    fecha_sesion: date | None,
    resultado: str,
    referencia_acta: str,
    observaciones: str = "",
    avisos_aceptados: Iterable[str] = (),
    hoy: date | None = None,
    crear_borrador: bool = True,
) -> Ratificacion:
    """APROBADO_CP → RATIFICADO_JG (o RECHAZADO). Registra fecha, resultado y referencia al acta."""
    _exigir_estado(version, EstadoVersion.APROBADO_CP)
    _exigir_puede_ratificar(contexto, version)
    if not version.requiere_junta:
        raise ValidationError("Esta versión no necesita ratificación de la Junta.")
    _exigir_integridad(contexto, version)
    aprobacion, fecha_conv = datos_ratificacion_previos(version)
    datos = DatosRatificacion(
        fecha=fecha_sesion,
        resultado=resultado,
        referencia_acta=referencia_acta,
        fecha_aprobacion_cp=aprobacion,
        fecha_convocatoria=fecha_conv,
    )
    hoy = hoy or timezone.localdate()
    bloqueos = o002(datos, hoy)
    if bloqueos:
        raise ValidationError([i.mensaje for i in bloqueos])
    avisos = o004(datos)
    sin_aceptar = {i.codigo for i in avisos} - set(avisos_aceptados)
    if sin_aceptar:
        raise ValidationError(
            [i.mensaje for i in avisos]
            + ["Acepta el aviso para dejar constancia y poder continuar."]
        )
    assert fecha_sesion is not None
    conv = Convocatoria.objects.filter(version=version).order_by("-id").first()
    r = Ratificacion.objects.create(
        version=version,
        fecha_sesion=fecha_sesion,
        resultado=resultado,
        referencia_acta=referencia_acta.strip(),
        observaciones=observaciones.strip(),
        convocatoria=conv,
        registrada_por=contexto.usuario,
        rol=contexto.rol_activo,
        es_demo=version.es_demo,
    )
    registrar(
        contexto,
        accion="ratificacion.registrar",
        entidad="Ratificacion",
        entidad_id=r.pk,
        despues={"resultado": resultado, "fecha_sesion": str(fecha_sesion)},
        es_demo=version.es_demo,
    )
    texto = f"Junta General del {fecha_sesion:%d/%m/%Y}, acta {referencia_acta.strip()}."
    if resultado == ResultadoRatificacion.RATIFICADO:
        _transitar(
            contexto,
            version,
            EstadoVersion.RATIFICADO_JG,
            motivo="Ratificada. " + texto,
            avisos=[i.codigo for i in avisos],
        )
    else:
        _transitar(
            contexto,
            version,
            EstadoVersion.RECHAZADO,
            motivo="Rechazada por la Junta General. " + texto,
            avisos=[i.codigo for i in avisos],
        )
        if crear_borrador:
            nuevo_borrador_desde(
                contexto,
                version,
                TipoOrigen.TRAS_RECHAZO,
                "Nuevo borrador tras el rechazo de la Junta General",
                _interno=True,
            )
    return r


# ------------------------------------------------------- nuevas versiones (copias)


def _copiar_contenido(
    origen: VersionPresupuesto,
    destino: VersionPresupuesto,
    *,
    filtro: Callable[[Linea], bool] = lambda ln: True,
) -> int:
    copiadas: dict[int, Linea] = {}
    for ln in (
        Linea.objects.filter(version=origen, anulada=False)
        .select_related("partida__capitulo")
        .order_by("codigo")
    ):
        if not filtro(ln):
            continue
        nueva = Linea.objects.create(
            version=destino,
            partida=ln.partida,
            codigo=ln.codigo,
            denominacion=ln.denominacion,
            cuenta_pgc=ln.cuenta_pgc,
            importe_anual=ln.importe_anual,
            tipo=ln.tipo,
            dimension=ln.dimension,
            importe_ejercicio_anterior=ln.importe_ejercicio_anterior,
            justificacion_variacion=ln.justificacion_variacion,
            responsable=ln.responsable,
            operaciones_altas=ln.operaciones_altas,
            origen_ingreso=ln.origen_ingreso,
            es_ajuste=ln.es_ajuste,
            justificacion_ajuste=ln.justificacion_ajuste,
        )
        copiadas[ln.pk] = nueva
        ImporteMensual.objects.bulk_create(
            ImporteMensual(linea=nueva, mes=m.mes, importe=m.importe)
            for m in ImporteMensual.objects.filter(linea=ln)
        )
        h = getattr(ln, "hipotesis", None)
        if h is not None:
            Hipotesis.objects.create(
                linea=nueva, texto=h.texto, fuente=h.fuente, confianza=h.confianza
            )
    for d in Donacion.objects.filter(version=origen, anulada=False).select_related("donante"):
        if d.linea_id in copiadas:
            Donacion.objects.create(
                version=destino,
                linea=copiadas[d.linea_id],
                donante=d.donante,
                importe=d.importe,
                tipo=d.tipo,
                finalista=d.finalista,
                revocable=d.revocable,
                es_demo=destino.es_demo,
            )
    return len(copiadas)


def _siguiente_numero(ejercicio: Ejercicio) -> int:
    ultimo = ejercicio.versiones.order_by("-numero").first()
    return (ultimo.numero if ultimo else 0) + 1


def nuevo_borrador_desde(
    contexto: Contexto,
    origen: VersionPresupuesto,
    tipo_origen: str,
    motivo: str,
    *,
    _interno: bool = False,
) -> VersionPresupuesto:
    """Crea un borrador con el contenido de ``origen`` (tras un rechazo o para una modificación)."""
    if not _interno:
        _exigir_rol(contexto, Rol.TESORERO)
    with transaction.atomic():
        nueva = VersionPresupuesto.objects.create(
            ejercicio=origen.ejercicio,
            numero=_siguiente_numero(origen.ejercicio),
            estado=EstadoVersion.BORRADOR,
            autor=contexto.usuario,
            motivo=motivo,
            version_origen=origen,
            tipo_origen=tipo_origen,
            explicacion_resultado=origen.explicacion_resultado,
            plan_financiacion=origen.plan_financiacion,
            endeudamiento_previsto=origen.endeudamiento_previsto,
            es_demo=origen.es_demo,
        )
        n = _copiar_contenido(origen, nueva)
        registrar(
            contexto,
            accion="version.crear_borrador",
            entidad="VersionPresupuesto",
            entidad_id=nueva.pk,
            despues={"origen": origen.pk, "tipo_origen": tipo_origen, "lineas": n},
            motivo=motivo,
            es_demo=origen.es_demo,
        )
    return nueva


@transaction.atomic
def crear_modificacion(
    contexto: Contexto, version: VersionPresupuesto, motivo: str
) -> VersionPresupuesto:
    """Nueva versión derivada de una aprobada, con su justificación (§5.3)."""
    _exigir_rol(contexto, Rol.TESORERO)
    _exigir_estado(version, *VIGENTES)
    if not motivo.strip():
        raise ValidationError("Una modificación presupuestaria exige justificación.")
    if version.ejercicio.versiones.filter(estado__in=ABIERTAS).exists():
        raise ValidationError("Ya hay una versión en curso en este ejercicio: termínala antes.")
    if vigente(version.ejercicio) != version:
        raise ValidationError("Solo se puede modificar la versión vigente del ejercicio.")
    return nuevo_borrador_desde(contexto, version, TipoOrigen.MODIFICACION, motivo.strip())


def prorroga_disponible(ejercicio: Ejercicio, hoy: date | None = None) -> tuple[bool, str]:
    """¿Se puede ofrecer la prórroga? (§5.2.5: a 1 de enero sin presupuesto ratificado)."""
    hoy = hoy or timezone.localdate()
    if hoy < date(ejercicio.anio, 1, 1):
        return False, f"Todavía no ha empezado el ejercicio {ejercicio.anio}."
    if vigente(ejercicio) is not None:
        return False, "El ejercicio ya tiene un presupuesto aprobado."
    if ejercicio.versiones.filter(tipo_origen=TipoOrigen.PRORROGA).exists():
        return False, "Ya se generó la prórroga de este ejercicio."
    anterior = Ejercicio.objects.filter(anio=ejercicio.anio - 1, es_demo=ejercicio.es_demo).first()
    if anterior is None or vigente(anterior) is None:
        return False, "No hay un presupuesto aprobado del ejercicio anterior que prorrogar."
    return True, ""


@transaction.atomic
def crear_prorroga(
    contexto: Contexto, ejercicio: Ejercicio, *, hoy: date | None = None
) -> VersionPresupuesto:
    """Presupuesto prorrogado del ejercicio anterior, marcado como provisional.

    Solo se copian las líneas recurrentes y se excluye todo lo de campaña: una campaña electoral
    es un gasto puntual y no se prorroga.
    """
    _exigir_rol(contexto, Rol.TESORERO)
    posible, motivo = prorroga_disponible(ejercicio, hoy)
    if not posible:
        raise ValidationError(motivo)
    anterior = Ejercicio.objects.get(anio=ejercicio.anio - 1, es_demo=ejercicio.es_demo)
    origen = vigente(anterior)
    assert origen is not None
    nueva = VersionPresupuesto.objects.create(
        ejercicio=ejercicio,
        numero=_siguiente_numero(ejercicio),
        estado=EstadoVersion.BORRADOR,
        autor=contexto.usuario,
        motivo=f"Prórroga provisional del presupuesto de {anterior.anio}",
        version_origen=origen,
        tipo_origen=TipoOrigen.PRORROGA,
        es_prorroga=True,
        explicacion_resultado=origen.explicacion_resultado,
        endeudamiento_previsto=CERO,
        es_demo=ejercicio.es_demo,
    )
    n = _copiar_contenido(
        origen,
        nueva,
        filtro=lambda ln: (
            ln.tipo == TipoLinea.RECURRENTE
            and ln.dimension != "CAMPANA"
            and ln.partida.capitulo.codigo != "G.7"
        ),
    )
    registrar(
        contexto,
        accion="version.prorroga",
        entidad="VersionPresupuesto",
        entidad_id=nueva.pk,
        despues={"origen": origen.pk, "lineas": n},
        es_demo=ejercicio.es_demo,
    )
    return nueva


# ------------------------------------------------------------------ comentarios


@transaction.atomic
def comentar(
    contexto: Contexto, version: VersionPresupuesto, texto: str, linea: Linea | None = None
) -> Comentario:
    _exigir_rol(contexto, Rol.COMISION_PERMANENTE, Rol.TESORERO)
    if not texto.strip():
        raise ValidationError("El comentario no puede estar vacío.")
    if linea is not None and linea.version_id != version.pk:
        raise ValidationError("Esa línea no es de esta versión.")
    usuario = contexto.usuario
    assert usuario is not None
    c = Comentario.objects.create(
        version=version,
        linea=linea,
        autor=usuario,
        rol_autor=contexto.rol_activo,
        texto=texto.strip(),
        es_demo=version.es_demo,
    )
    registrar(
        contexto,
        accion="comentario.crear",
        entidad="Comentario",
        entidad_id=c.pk,
        despues={"version": version.pk, "linea": linea.codigo if linea else None},
        es_demo=version.es_demo,
    )
    return c


@transaction.atomic
def resolver_comentario(contexto: Contexto, comentario: Comentario) -> None:
    _exigir_rol(contexto, Rol.COMISION_PERMANENTE, Rol.TESORERO)
    if comentario.resuelto:
        return
    comentario.resuelto = True
    comentario.resuelto_por = contexto.usuario
    comentario.fecha_resuelto = timezone.now()
    comentario.save()
    registrar(
        contexto,
        accion="comentario.resolver",
        entidad="Comentario",
        entidad_id=comentario.pk,
        es_demo=comentario.es_demo,
    )
