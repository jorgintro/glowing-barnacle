from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.auditoria.servicios import Contexto
from apps.usuarios.decoradores import requiere_rol
from apps.usuarios.roles import Rol

from . import servicios
from .forms import BajaPersonaForm, CargosForm, OrganizacionForm, PersonaForm
from .models import Organizacion, Persona


@requiere_rol(Rol.TESORERO)
def panel(request: HttpRequest) -> HttpResponse:
    org = Organizacion.obtener()
    return render(
        request,
        "organizacion/panel.html",
        {
            "form_org": OrganizacionForm(
                initial={
                    "nombre": org.nombre,
                    "localidad": org.localidad,
                    "denominacion_tesoreria": org.denominacion_tesoreria,
                }
            ),
            "form_cargos": CargosForm(initial={"cargos": servicios.texto_de_cargos()}),
            "personas": Persona.objects.filter(es_demo=False).order_by("-activa", "apellidos"),
            "personas_demo": Persona.objects.filter(es_demo=True).order_by("apellidos"),
        },
    )


@requiere_rol(Rol.TESORERO)
def guardar_datos(request: HttpRequest) -> HttpResponse:
    form = OrganizacionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            servicios.guardar_organizacion(Contexto.desde_request(request), **form.cleaned_data)
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)
        else:
            messages.success(request, "Datos de la organización guardados.")
    elif request.method == "POST":
        messages.error(request, "Revisa los datos de la organización: falta algo.")
    return redirect("organizacion:panel")


@requiere_rol(Rol.TESORERO)
def guardar_cargos(request: HttpRequest) -> HttpResponse:
    form = CargosForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        resultado = servicios.sincronizar_cargos(
            Contexto.desde_request(request), form.cleaned_data["cargos"]
        )
        messages.success(
            request,
            f"Cargos guardados: {resultado['creados']} nuevos, {resultado['reactivados']} "
            f"reactivados y {resultado['desactivados']} desactivados.",
        )
    return redirect("organizacion:panel")


def _guardar_persona(request: HttpRequest, persona: Persona | None) -> HttpResponse:
    inicial = PersonaForm.inicial_desde(persona) if persona else None
    form = PersonaForm(request.POST or None, initial=inicial, persona=persona)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            if persona is None:
                servicios.crear_persona(
                    Contexto.desde_request(request),
                    nombre=d["nombre"],
                    apellidos=d["apellidos"],
                    dni=d["dni"],
                    cargos=d["cargos"],
                    usuario=d["usuario"],
                )
            else:
                servicios.actualizar_persona(
                    Contexto.desde_request(request),
                    persona,
                    nombre=d["nombre"],
                    apellidos=d["apellidos"],
                    dni=d["dni"],
                    cargos=d["cargos"],
                    usuario=d["usuario"],
                )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Persona guardada.")
            return redirect("organizacion:panel")
    return render(request, "organizacion/persona_form.html", {"form": form, "persona": persona})


@requiere_rol(Rol.TESORERO)
def persona_nueva(request: HttpRequest) -> HttpResponse:
    return _guardar_persona(request, None)


@requiere_rol(Rol.TESORERO)
def persona_editar(request: HttpRequest, pk: int) -> HttpResponse:
    persona = get_object_or_404(Persona, pk=pk)
    if not persona.activa:
        messages.error(request, "Esa persona está de baja y no se puede modificar.")
        return redirect("organizacion:panel")
    return _guardar_persona(request, persona)


@requiere_rol(Rol.TESORERO)
def persona_baja(request: HttpRequest, pk: int) -> HttpResponse:
    persona = get_object_or_404(Persona, pk=pk)
    form = BajaPersonaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            servicios.dar_de_baja_persona(
                Contexto.desde_request(request), persona, form.cleaned_data["motivo"]
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Persona dada de baja (se conserva en el historial).")
            return redirect("organizacion:panel")
    return render(request, "organizacion/persona_baja.html", {"persona": persona, "form": form})
