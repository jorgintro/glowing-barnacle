from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.servicios import Contexto
from apps.presupuesto.configuracion import ErrorConfiguracion, cargar_configuracion
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import Comentario, Ejercicio, VersionPresupuesto
from apps.presupuesto.permisos import versiones_visibles
from apps.usuarios.decoradores import requiere_rol
from apps.usuarios.roles import Rol
from apps.validaciones.motor import validar_version
from apps.validaciones.reglas_o import evaluar_votacion, o003

from . import servicios as fs
from .forms import (
    CerrarVotacionForm,
    ComentarioForm,
    ConvocatoriaForm,
    FiltroAuditoriaForm,
    MotivoForm,
    ProponerForm,
    RatificarForm,
    VotarForm,
)
from .models import EstadoVotacion, Votacion
from .panel import contexto_flujo, nombre_miembro
from .sello import verificar_integridad

TODOS = (Rol.TESORERO, Rol.COMISION_PERMANENTE, Rol.JUNTA_GENERAL)


def _visible(request: HttpRequest, pk: int) -> VersionPresupuesto:
    v = versiones_visibles(request.rol_activo).filter(pk=pk).first()  # type: ignore[attr-defined]
    if v is None:
        raise Http404("Versión no disponible con tu rol.")
    return v


def _ctx(request: HttpRequest) -> Contexto:
    return Contexto.desde_request(request)


def _errores(request: HttpRequest, error: Exception) -> None:
    if isinstance(error, ValidationError):
        for m in error.messages:
            messages.error(request, m)
    else:
        messages.error(request, str(error))


# ----------------------------------------------------------------------- proponer


@requiere_rol(Rol.TESORERO)
def proponer(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    if v.estado != EstadoVersion.BORRADOR:
        messages.error(request, "Solo se puede proponer un borrador.")
        return redirect("presupuesto:version", pk=v.pk)
    resultado = validar_version(v)
    form = ProponerForm(
        request.POST or None,
        avisos=[(i.codigo, f"{i.codigo} · {i.mensaje}") for i in resultado.avisos],
    )
    if request.method == "POST" and form.is_valid():
        try:
            fs.proponer(
                _ctx(request),
                v,
                avisos_aceptados=form.cleaned_data["avisos"],
                confirmar=form.cleaned_data["confirmar"],
            )
        except (ValidationError, PermissionDenied) as error:
            _errores(request, error)
        else:
            messages.success(request, "Versión propuesta y sellada. La votación está abierta.")
            return redirect("flujo:votacion", pk=v.pk)
    return render(
        request, "flujo/proponer.html", {"version": v, "resultado": resultado, "form": form}
    )


# ----------------------------------------------------------------------- generico


def _formulario(
    request: HttpRequest,
    v: VersionPresupuesto,
    form: Any,
    *,
    titulo: str,
    intro: str,
    boton: str,
) -> HttpResponse:
    return render(
        request,
        "flujo/formulario.html",
        {"version": v, "form": form, "titulo": titulo, "intro": intro, "boton": boton},
    )


@requiere_rol(Rol.COMISION_PERMANENTE)
def devolver(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    form = MotivoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            fs.devolver(_ctx(request), v, form.cleaned_data["motivo"])
        except (ValidationError, PermissionDenied, fs.IntegridadRota) as error:
            _errores(request, error)
        else:
            messages.success(request, "Propuesta devuelta al Tesorero con tus motivos.")
            return redirect("presupuesto:version", pk=v.pk)
    return _formulario(
        request,
        v,
        form,
        titulo="Devolver la propuesta al Tesorero",
        intro="La versión vuelve a ser un borrador editable. El Tesorero verá tus motivos.",
        boton="Devolver con estos motivos",
    )


# ----------------------------------------------------------------------- votación


@requiere_rol(*TODOS)
def votacion(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    vot = v.votaciones.order_by("-id").first()
    if vot is None:
        messages.error(request, "Esta versión todavía no tiene votación.")
        return redirect("presupuesto:version", pk=v.pk)
    votos = {x.usuario_id: x for x in vot.votos.select_related("usuario")}
    miembros = list(fs.miembros_cp(v.es_demo).order_by("username"))
    filas = [
        {
            "nombre": nombre_miembro(m),
            "voto": votos.get(m.pk),
            "es_proponente": m.pk == v.proponente_id,
        }
        for m in miembros
    ]
    datos = fs.datos_votacion(vot)
    try:
        org = cargar_configuracion(v.es_demo).organicas
        evaluacion = evaluar_votacion(datos, org)
        prohibido = o003(datos, org)
    except ErrorConfiguracion:
        evaluacion, prohibido = None, []
    flujo = contexto_flujo(request, v)
    mi_voto = votos.get(request.user.pk or 0)
    return render(
        request,
        "flujo/votacion.html",
        {
            "version": v,
            "votacion": vot,
            "filas": filas,
            "datos": datos,
            "evaluacion": evaluacion,
            "prohibido": prohibido,
            "flujo": flujo,
            "form_votar": VotarForm(initial={"voto": mi_voto.voto if mi_voto else None}),
            "form_cerrar": CerrarVotacionForm(),
            "mi_voto": mi_voto,
        },
    )


@requiere_rol(Rol.COMISION_PERMANENTE)
@require_POST
def votar(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    vot = get_object_or_404(Votacion, version=v, estado=EstadoVotacion.ABIERTA)
    form = VotarForm(request.POST)
    if form.is_valid():
        try:
            fs.votar(_ctx(request), vot, form.cleaned_data["voto"])
        except (ValidationError, PermissionDenied) as error:
            _errores(request, error)
        else:
            messages.success(request, "Tu voto ha quedado registrado.")
    else:
        messages.error(request, "Elige una opción de voto.")
    return redirect("flujo:votacion", pk=v.pk)


@requiere_rol(Rol.COMISION_PERMANENTE)
@require_POST
def cerrar_votacion(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    vot = get_object_or_404(Votacion, version=v, estado=EstadoVotacion.ABIERTA)
    form = CerrarVotacionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Debes confirmar el cierre de la votación.")
        return redirect("flujo:votacion", pk=v.pk)
    try:
        cerrada = fs.cerrar_votacion(_ctx(request), vot, form.cleaned_data["observaciones"])
    except (ValidationError, PermissionDenied, fs.IntegridadRota) as error:
        _errores(request, error)
    else:
        messages.success(request, f"Votación cerrada: {cerrada.get_resultado_display().lower()}.")
    return redirect("flujo:votacion", pk=v.pk)


# ------------------------------------------------------------------------ Junta


@requiere_rol(Rol.TESORERO, Rol.JUNTA_GENERAL)
def convocatoria(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    form = ConvocatoriaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            fs.registrar_convocatoria(_ctx(request), v, **form.cleaned_data)
        except (ValidationError, PermissionDenied) as error:
            _errores(request, error)
        else:
            messages.success(request, "Convocatoria de la Junta registrada.")
            return redirect("presupuesto:version", pk=v.pk)
    return _formulario(
        request,
        v,
        form,
        titulo="Registrar la convocatoria de la Junta General",
        intro="Debe constar antes de registrar la ratificación (regla O-004).",
        boton="Registrar la convocatoria",
    )


@requiere_rol(Rol.TESORERO, Rol.JUNTA_GENERAL)
def ratificar(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    previa_aprobacion, previa_convocatoria = fs.datos_ratificacion_previos(v)
    form = RatificarForm(request.POST or None, initial={"fecha_sesion": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            fs.registrar_ratificacion(
                _ctx(request),
                v,
                fecha_sesion=d["fecha_sesion"],
                resultado=d["resultado"],
                referencia_acta=d["referencia_acta"],
                observaciones=d["observaciones"],
                avisos_aceptados=["O-004"] if d["acepto_aviso"] else [],
            )
        except (ValidationError, PermissionDenied, fs.IntegridadRota) as error:
            _errores(request, error)
        else:
            messages.success(request, "Acuerdo de la Junta registrado.")
            return redirect("presupuesto:version", pk=v.pk)
    return render(
        request,
        "flujo/ratificar.html",
        {
            "version": v,
            "form": form,
            "sin_convocatoria": previa_convocatoria is None,
            "aprobacion": previa_aprobacion,
        },
    )


# ------------------------------------------------------- modificación y prórroga


@requiere_rol(Rol.TESORERO)
def modificar(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    form = MotivoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            nueva = fs.crear_modificacion(_ctx(request), v, form.cleaned_data["motivo"])
        except (ValidationError, PermissionDenied) as error:
            _errores(request, error)
        else:
            messages.success(
                request, "Borrador de modificación creado a partir de la versión vigente."
            )
            return redirect("presupuesto:version", pk=nueva.pk)
    return _formulario(
        request,
        v,
        form,
        titulo="Crear una modificación presupuestaria",
        intro="Se crea un borrador nuevo con el contenido de esta versión. Repite el ciclo de "
        "aprobación; si supera el umbral de los estatutos o el reglamento, volverá a la Junta.",
        boton="Crear el borrador de modificación",
    )


@requiere_rol(Rol.TESORERO)
@require_POST
def prorroga(request: HttpRequest, pk: int) -> HttpResponse:
    ejercicio = get_object_or_404(Ejercicio, pk=pk)
    try:
        nueva = fs.crear_prorroga(_ctx(request), ejercicio)
    except (ValidationError, PermissionDenied) as error:
        _errores(request, error)
        return redirect("presupuesto:lista")
    messages.success(request, "Prórroga provisional creada como borrador.")
    return redirect("presupuesto:version", pk=nueva.pk)


# ------------------------------------------------------------------- historial


@requiere_rol(*TODOS)
def historial(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    return render(
        request,
        "flujo/historial.html",
        {
            "version": v,
            "transiciones": v.transiciones.select_related("usuario").order_by("id"),
            "votaciones": v.votaciones.order_by("id"),
            "convocatorias": v.convocatorias.order_by("id"),
            "ratificacion": getattr(v, "ratificacion", None),
            "integridad": verificar_integridad(v),
        },
    )


# ------------------------------------------------------------------ comentarios


@requiere_rol(Rol.TESORERO, Rol.COMISION_PERMANENTE)
def comentarios(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    if v.estado == EstadoVersion.BORRADOR:
        messages.error(request, "Los comentarios empiezan cuando la versión se propone.")
        return redirect("presupuesto:version", pk=v.pk)
    form = ComentarioForm(request.POST or None, version=v)
    if request.method == "POST" and form.is_valid():
        try:
            fs.comentar(_ctx(request), v, form.cleaned_data["texto"], form.cleaned_data["linea"])
        except (ValidationError, PermissionDenied) as error:
            _errores(request, error)
        else:
            messages.success(request, "Comentario añadido.")
            return redirect("flujo:comentarios", pk=v.pk)
    return render(
        request,
        "flujo/comentarios.html",
        {
            "version": v,
            "form": form,
            "lista": v.comentarios.select_related("autor", "linea", "resuelto_por").order_by(
                "fecha"
            ),
        },
    )


@requiere_rol(Rol.TESORERO, Rol.COMISION_PERMANENTE)
@require_POST
def resolver_comentario(request: HttpRequest, pk: int, comentario_pk: int) -> HttpResponse:
    v = _visible(request, pk)
    c = get_object_or_404(Comentario, pk=comentario_pk, version=v)
    try:
        fs.resolver_comentario(_ctx(request), c)
    except PermissionDenied as error:
        _errores(request, error)
    else:
        messages.success(request, "Comentario marcado como resuelto.")
    return redirect("flujo:comentarios", pk=v.pk)


# ------------------------------------------------------------------- auditoría


@requiere_rol(Rol.TESORERO)
def auditoria(request: HttpRequest) -> HttpResponse:
    form = FiltroAuditoriaForm(request.GET or None)
    registros = RegistroAuditoria.objects.select_related("usuario").all()
    if form.is_valid():
        d = form.cleaned_data
        if d["usuario"]:
            registros = registros.filter(usuario_texto__icontains=d["usuario"])
        if d["accion"]:
            registros = registros.filter(accion__icontains=d["accion"])
        if d["entidad"]:
            registros = registros.filter(entidad__icontains=d["entidad"])
        if d["desde"]:
            registros = registros.filter(fecha__date__gte=d["desde"])
        if d["hasta"]:
            registros = registros.filter(fecha__date__lte=d["hasta"])
    pagina = Paginator(registros.order_by("-fecha", "-id"), 50).get_page(request.GET.get("pagina"))
    consulta = request.GET.copy()
    consulta.pop("pagina", None)
    return render(
        request,
        "flujo/auditoria.html",
        {"form": form, "pagina": pagina, "consulta": consulta.urlencode()},
    )
