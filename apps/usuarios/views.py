from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.auditoria.servicios import Contexto, registrar

from . import servicios
from .decoradores import requiere_rol
from .forms import BajaForm, CrearUsuarioForm, EditarRolesForm
from .middleware import CLAVE_SESION
from .models import Usuario
from .roles import DESCRIPCION_ROL, Rol


class EntrarView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True


@login_required
def inicio(request: HttpRequest) -> HttpResponse:
    rol = request.rol_activo  # type: ignore[attr-defined]
    return render(request, "inicio.html", {"descripcion": DESCRIPCION_ROL.get(rol, {})})


@login_required
def seleccionar_rol(request: HttpRequest) -> HttpResponse:
    asignados = request.user.roles_vigentes()  # type: ignore[union-attr]
    if request.method == "POST":
        elegido = request.POST.get("rol")
        if elegido in asignados:
            anterior = request.session.get(CLAVE_SESION)
            request.session[CLAVE_SESION] = elegido
            request.rol_activo = elegido  # type: ignore[attr-defined]
            registrar(
                Contexto.desde_request(request),
                accion="sesion.seleccionar_rol",
                entidad="Usuario",
                entidad_id=request.user.pk,
                antes={"rol": anterior},
                despues={"rol": elegido},
            )
            return redirect("inicio")
        messages.error(request, "Ese rol no está asignado a tu usuario.")
    roles = [{"clave": r, "nombre": Rol(r).label, **DESCRIPCION_ROL[r]} for r in asignados]
    return render(request, "usuarios/seleccionar_rol.html", {"roles": roles})


@require_POST
def salir(request: HttpRequest) -> HttpResponse:
    from django.contrib.auth import logout

    logout(request)
    return redirect("usuarios:entrar")


@requiere_rol(Rol.TESORERO)
def lista(request: HttpRequest) -> HttpResponse:
    usuarios = Usuario.objects.order_by("-is_active", "username")
    filas = [{"usuario": u, "roles": [Rol(r).label for r in u.roles_vigentes()]} for u in usuarios]
    return render(request, "usuarios/lista.html", {"filas": filas})


@requiere_rol(Rol.TESORERO)
def crear(request: HttpRequest) -> HttpResponse:
    form = CrearUsuarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        servicios.crear_usuario(Contexto.desde_request(request), **datos)
        messages.success(request, f"Usuario «{datos['username']}» creado.")
        return redirect("usuarios:lista")
    return render(request, "usuarios/crear.html", {"form": form})


@requiere_rol(Rol.TESORERO)
def editar(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_object_or_404(Usuario, pk=pk)
    form = EditarRolesForm(request.POST or None, initial={"roles": usuario.roles_vigentes()})
    if request.method == "POST" and form.is_valid():
        try:
            servicios.actualizar_roles(
                Contexto.desde_request(request),
                usuario,
                form.cleaned_data["roles"],
                form.cleaned_data["motivo"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Roles actualizados.")
            return redirect("usuarios:lista")
    return render(request, "usuarios/editar.html", {"form": form, "usuario_editado": usuario})


@requiere_rol(Rol.TESORERO)
def baja(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_object_or_404(Usuario, pk=pk)
    form = BajaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            servicios.dar_de_baja(
                Contexto.desde_request(request), usuario, form.cleaned_data["motivo"]
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Usuario dado de baja.")
            return redirect("usuarios:lista")
    return render(request, "usuarios/baja.html", {"form": form, "usuario_editado": usuario})
