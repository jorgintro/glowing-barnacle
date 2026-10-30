"""Qué puede hacer cada usuario con una versión (panel del flujo) y nombres para mostrar."""

from typing import Any

from django.http import HttpRequest

from apps.organizacion.models import Persona
from apps.presupuesto.configuracion import ErrorConfiguracion, cargar_configuracion
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import VersionPresupuesto
from apps.usuarios.models import Usuario
from apps.usuarios.roles import Rol

from . import servicios as fs
from .models import EstadoVotacion


def nombre_miembro(usuario: Usuario) -> str:
    """Nombre para mostrar: la ficha del panel si la hay (con cargos) o el nombre de la cuenta."""
    persona = Persona.objects.filter(usuario=usuario).first()
    if persona is not None:
        cargos = persona.cargos_texto()
        return f"{persona.nombre_completo} ({cargos})" if cargos else persona.nombre_completo
    return usuario.nombre_visible()


def contexto_flujo(request: HttpRequest, v: VersionPresupuesto) -> dict[str, Any]:
    """Qué acciones del flujo tiene a su alcance el usuario actual sobre esta versión."""
    rol = getattr(request, "rol_activo", None)
    try:
        ratifican = cargar_configuracion(v.es_demo).organicas.ratificacion_registrada_por
    except ErrorConfiguracion:
        ratifican = ("JUNTA_GENERAL",)
    votacion = v.votaciones.order_by("-id").first()
    abierta = (
        votacion is not None
        and votacion.estado == EstadoVotacion.ABIERTA
        and v.estado == EstadoVersion.PROPUESTO
    )
    es_cp = rol == Rol.COMISION_PERMANENTE
    es_miembro = es_cp and fs.miembros_cp(v.es_demo).filter(pk=request.user.pk or 0).exists()
    esperando_junta = v.estado == EstadoVersion.APROBADO_CP and v.requiere_junta
    return {
        "votacion": votacion,
        "puede_proponer": rol == Rol.TESORERO and v.estado == EstadoVersion.BORRADOR,
        "puede_devolver": es_cp and v.estado == EstadoVersion.PROPUESTO,
        "puede_votar": es_miembro and abierta,
        "puede_cerrar": es_cp and abierta,
        "ver_votacion": votacion is not None,
        "puede_convocar": esperando_junta and rol in (Rol.TESORERO, Rol.JUNTA_GENERAL),
        "puede_ratificar": esperando_junta and rol in ratifican,
        "puede_modificar": rol == Rol.TESORERO
        and v.estado in fs.VIGENTES
        and fs.vigente(v.ejercicio) == v
        and not v.ejercicio.versiones.filter(estado__in=fs.ABIERTAS).exists(),
        "puede_comentar": rol in (Rol.TESORERO, Rol.COMISION_PERMANENTE)
        and v.estado != EstadoVersion.BORRADOR,
        "ultimo_comentario_abierto": v.comentarios.filter(resuelto=False).count(),
        "certificables": v.estado
        in (
            EstadoVersion.APROBADO_CP,
            EstadoVersion.RATIFICADO_JG,
            EstadoVersion.MODIFICADO,
        ),
    }
