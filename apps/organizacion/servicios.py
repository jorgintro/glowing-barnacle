"""Gestión del panel de administración. Solo el Tesorero; todo queda en la auditoría.

La auditoría no guarda DNI ni nombres (no se puede borrar y chocaría con el derecho de supresión):
solo identificadores internos.
"""

from collections.abc import Iterable

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.servicios import Contexto, registrar
from apps.presupuesto.nif import validar_nif
from apps.usuarios.models import Usuario
from apps.usuarios.roles import Rol

from .models import Cargo, Organizacion, Persona


def _exigir_tesorero(contexto: Contexto) -> None:
    if contexto.usuario is None or contexto.rol_activo != Rol.TESORERO:
        raise PermissionDenied("Solo el Tesorero puede administrar los datos de la organización.")


@transaction.atomic
def guardar_organizacion(
    contexto: Contexto, *, nombre: str, localidad: str, denominacion_tesoreria: str
) -> Organizacion:
    _exigir_tesorero(contexto)
    errores = []
    if not nombre.strip():
        errores.append("Falta el nombre de la organización.")
    if not localidad.strip():
        errores.append("Falta la localidad.")
    if not denominacion_tesoreria.strip():
        errores.append("Falta cómo se llama el cargo de Tesorería.")
    if errores:
        raise ValidationError(errores)
    org = Organizacion.obtener()
    antes = {"tesoreria": org.denominacion_tesoreria}
    org.nombre, org.localidad = nombre.strip(), localidad.strip()
    org.denominacion_tesoreria = denominacion_tesoreria.strip()
    org.save()
    registrar(
        contexto,
        accion="organizacion.guardar",
        entidad="Organizacion",
        entidad_id=org.pk,
        antes=antes,
        despues={"tesoreria": org.denominacion_tesoreria},
    )
    return org


def _lineas(texto: str) -> list[str]:
    vistas: dict[str, str] = {}
    for linea in texto.splitlines():
        limpia = " ".join(linea.split())
        if limpia:
            vistas.setdefault(limpia.casefold(), limpia)
    return list(vistas.values())


@transaction.atomic
def sincronizar_cargos(contexto: Contexto, texto: str) -> dict[str, int]:
    """Deja como activos exactamente los cargos escritos (uno por línea). No borra ninguno."""
    _exigir_tesorero(contexto)
    deseados = _lineas(texto)
    creados = reactivados = desactivados = 0
    existentes = {c.denominacion.casefold(): c for c in Cargo.objects.all()}
    for orden, nombre in enumerate(deseados, start=1):
        cargo = existentes.get(nombre.casefold())
        if cargo is None:
            Cargo.objects.create(denominacion=nombre, orden=orden)
            creados += 1
        else:
            cambios = []
            if not cargo.activo:
                cargo.activo = True
                cambios.append("activo")
                reactivados += 1
            if cargo.orden != orden or cargo.denominacion != nombre:
                cargo.orden, cargo.denominacion = orden, nombre
                cambios.append("orden")
            if cambios:
                cargo.save()
    claves = {n.casefold() for n in deseados}
    for clave, cargo in existentes.items():
        if clave not in claves and cargo.activo:
            cargo.activo = False
            cargo.save(update_fields=["activo"])
            desactivados += 1
    resultado = {"creados": creados, "reactivados": reactivados, "desactivados": desactivados}
    if any(resultado.values()):
        registrar(
            contexto,
            accion="cargos.sincronizar",
            entidad="Cargo",
            despues={**resultado, "total_activos": len(deseados)},
        )
    return resultado


def texto_de_cargos() -> str:
    return "\n".join(Cargo.objects.filter(activo=True).values_list("denominacion", flat=True))


def _validar_persona(
    nombre: str,
    apellidos: str,
    dni: str,
    cargos: Iterable[Cargo],
    usuario: Usuario | None,
    excluir: Persona | None,
    es_demo: bool,
) -> str:
    errores = []
    if not nombre.strip():
        errores.append("Falta el nombre.")
    if not apellidos.strip():
        errores.append("Faltan los apellidos.")
    dni_ok = ""
    try:
        dni_ok = validar_nif(dni, "FISICA")
    except ValidationError as error:
        errores.extend(error.messages)
    if dni_ok:
        repetida = Persona.objects.filter(dni=dni_ok, es_demo=es_demo)
        if excluir is not None:
            repetida = repetida.exclude(pk=excluir.pk)
        if repetida.exists():
            errores.append("Ya hay una persona con ese DNI.")
    if any(not c.activo for c in cargos):
        errores.append("Hay un cargo que ya no está activo.")
    if usuario is not None:
        ocupado = Persona.objects.filter(usuario=usuario)
        if excluir is not None:
            ocupado = ocupado.exclude(pk=excluir.pk)
        if ocupado.exists():
            errores.append("Esa cuenta de usuario ya está asignada a otra persona.")
    if errores:
        raise ValidationError(errores)
    return dni_ok


@transaction.atomic
def crear_persona(
    contexto: Contexto,
    *,
    nombre: str,
    apellidos: str,
    dni: str,
    cargos: Iterable[Cargo] = (),
    usuario: Usuario | None = None,
    es_demo: bool = False,
) -> Persona:
    _exigir_tesorero(contexto)
    cargos = list(cargos)
    dni_ok = _validar_persona(nombre, apellidos, dni, cargos, usuario, None, es_demo)
    persona = Persona.objects.create(
        nombre=nombre.strip(),
        apellidos=apellidos.strip(),
        dni=dni_ok,
        usuario=usuario,
        es_demo=es_demo,
    )
    persona.cargos.set(cargos)
    registrar(
        contexto,
        accion="persona.crear",
        entidad="Persona",
        entidad_id=persona.pk,
        despues={
            "cargos": sorted(c.pk for c in cargos),
            "usuario_id": usuario.pk if usuario else None,
        },
        es_demo=es_demo,
    )
    return persona


@transaction.atomic
def actualizar_persona(
    contexto: Contexto,
    persona: Persona,
    *,
    nombre: str,
    apellidos: str,
    dni: str,
    cargos: Iterable[Cargo] = (),
    usuario: Usuario | None = None,
) -> Persona:
    _exigir_tesorero(contexto)
    if not persona.activa:
        raise ValidationError("Esa persona está de baja y no se puede modificar.")
    cargos = list(cargos)
    dni_ok = _validar_persona(nombre, apellidos, dni, cargos, usuario, persona, persona.es_demo)
    antes = {
        "cargos": sorted(persona.cargos.values_list("pk", flat=True)),
        "usuario_id": persona.usuario_id,
    }
    persona.nombre, persona.apellidos, persona.dni = nombre.strip(), apellidos.strip(), dni_ok
    persona.usuario = usuario
    persona.save()
    persona.cargos.set(cargos)
    registrar(
        contexto,
        accion="persona.modificar",
        entidad="Persona",
        entidad_id=persona.pk,
        antes=antes,
        despues={
            "cargos": sorted(c.pk for c in cargos),
            "usuario_id": usuario.pk if usuario else None,
        },
        es_demo=persona.es_demo,
    )
    return persona


@transaction.atomic
def dar_de_baja_persona(contexto: Contexto, persona: Persona, motivo: str) -> None:
    _exigir_tesorero(contexto)
    if not motivo.strip():
        raise ValidationError("Para dar de baja a una persona hay que indicar el motivo.")
    if not persona.activa:
        return
    persona.activa = False
    persona.fecha_baja = timezone.now()
    persona.motivo_baja = motivo.strip()
    persona.save(update_fields=["activa", "fecha_baja", "motivo_baja"])
    registrar(
        contexto,
        accion="persona.baja",
        entidad="Persona",
        entidad_id=persona.pk,
        motivo=motivo,
        es_demo=persona.es_demo,
    )
