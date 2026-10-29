from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.auditoria.servicios import Contexto
from apps.usuarios.decoradores import requiere_rol
from apps.usuarios.roles import Rol

from . import servicios
from .calculos import resumen_version
from .configuracion import cargar_cuadro_cuentas
from .errores import VersionNoEditable
from .forms import MESES, AnularLineaForm, EjercicioForm, LineaForm
from .models import Capitulo, Ejercicio, Linea, ParametroLegal, Partida, VersionPresupuesto
from .permisos import versiones_visibles

TODOS = (Rol.TESORERO, Rol.COMISION_PERMANENTE, Rol.JUNTA_GENERAL)


def _version_visible(request: HttpRequest, pk: int) -> VersionPresupuesto:
    version = versiones_visibles(request.rol_activo).filter(pk=pk).first()  # type: ignore[attr-defined]
    if version is None:
        raise Http404("Versión no disponible con tu rol.")
    return version


def _version_borrador(pk: int) -> VersionPresupuesto:
    return get_object_or_404(VersionPresupuesto.objects.select_related("ejercicio"), pk=pk)


@requiere_rol(*TODOS)
def lista(request: HttpRequest) -> HttpResponse:
    visibles = versiones_visibles(request.rol_activo).order_by("ejercicio", "numero")  # type: ignore[attr-defined]
    por_ejercicio: dict[int, list[VersionPresupuesto]] = {}
    for v in visibles:
        por_ejercicio.setdefault(v.ejercicio_id, []).append(v)
    ejercicios = Ejercicio.objects.filter(pk__in=por_ejercicio).order_by("-anio", "es_demo")
    filas = [{"ejercicio": e, "versiones": por_ejercicio[e.pk]} for e in ejercicios]
    sin_versiones = []
    if request.rol_activo == Rol.TESORERO:  # type: ignore[attr-defined]
        sin_versiones = list(Ejercicio.objects.exclude(pk__in=por_ejercicio))
    return render(request, "presupuesto/lista.html", {"filas": filas, "vacios": sin_versiones})


@requiere_rol(Rol.TESORERO)
def ejercicio_nuevo(request: HttpRequest) -> HttpResponse:
    form = EjercicioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            _, version = servicios.crear_ejercicio(
                Contexto.desde_request(request), **form.cleaned_data
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Ejercicio creado con su primer borrador.")
            return redirect("presupuesto:version", pk=version.pk)
    return render(request, "presupuesto/ejercicio_nuevo.html", {"form": form})


@requiere_rol(*TODOS)
def version(request: HttpRequest, pk: int) -> HttpResponse:
    v = _version_visible(request, pk)
    resumen = resumen_version(v)
    lineas = (
        Linea.objects.filter(version=v)
        .select_related("partida", "cuenta_pgc", "hipotesis")
        .order_by("codigo")
    )
    por_capitulo: dict[str, list[Linea]] = {}
    for linea in lineas:
        por_capitulo.setdefault(linea.partida.capitulo.codigo, []).append(linea)
    bloques: list[dict[str, Any]] = [
        {"total": t, "lineas": por_capitulo.get(t.capitulo.codigo, [])}
        for t in resumen.capitulos
        if not t.capitulo.solo_con_proceso_electoral
        or v.ejercicio.hay_proceso_electoral
        or por_capitulo.get(t.capitulo.codigo)
    ]
    puede_editar = request.rol_activo == Rol.TESORERO and v.editable  # type: ignore[attr-defined]
    return render(
        request,
        "presupuesto/version.html",
        {
            "version": v,
            "resumen": resumen,
            "ingresos": [b for b in bloques if b["total"].capitulo.tipo == "INGRESO"],
            "gastos": [b for b in bloques if b["total"].capitulo.tipo == "GASTO"],
            "meses": MESES,
            "puede_editar": puede_editar,
            "otras_versiones": v.ejercicio.versiones.exclude(pk=v.pk),
        },
    )


@requiere_rol(Rol.TESORERO)
def linea_elegir_partida(request: HttpRequest, pk: int) -> HttpResponse:
    v = _version_borrador(pk)
    if not v.editable:
        messages.error(request, "Esta versión es de solo lectura.")
        return redirect("presupuesto:version", pk=v.pk)
    capitulos = Capitulo.objects.filter(activo=True).prefetch_related("partidas")
    if not v.ejercicio.hay_proceso_electoral:
        capitulos = capitulos.filter(solo_con_proceso_electoral=False)
    return render(
        request, "presupuesto/elegir_partida.html", {"version": v, "capitulos": capitulos}
    )


def _guardar(
    request: HttpRequest, v: VersionPresupuesto, partida: Partida, linea: Linea | None
) -> HttpResponse:
    inicial = LineaForm.inicial_desde(linea) if linea else None
    form = LineaForm(request.POST or None, partida=partida, initial=inicial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            servicios.guardar_linea(
                Contexto.desde_request(request),
                v,
                linea=linea,
                partida=partida,
                denominacion=d["denominacion"],
                cuenta=d["cuenta"],
                importe_anual=d["importe_anual"],
                hipotesis=servicios.DatosHipotesis(
                    d["hipotesis_texto"], d["hipotesis_fuente"], d["confianza"]
                ),
                responsable=d["responsable"],
                mensual=form.mensual(),
                tipo=d["tipo"],
                dimension=d["dimension"],
                importe_anterior=d["importe_anterior"],
                justificacion_variacion=d["justificacion_variacion"],
                es_ajuste=d["es_ajuste"],
                justificacion_ajuste=d["justificacion_ajuste"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        except VersionNoEditable as error:
            messages.error(request, str(error))
            return redirect("presupuesto:version", pk=v.pk)
        else:
            messages.success(request, "Línea guardada.")
            return redirect("presupuesto:version", pk=v.pk)
    return render(
        request,
        "presupuesto/linea_form.html",
        {"version": v, "partida": partida, "form": form, "linea": linea},
    )


@requiere_rol(Rol.TESORERO)
def linea_nueva(request: HttpRequest, pk: int, partida: str) -> HttpResponse:
    v = _version_borrador(pk)
    p = get_object_or_404(Partida, codigo=partida, activa=True)
    if not v.editable:
        return redirect("presupuesto:version", pk=v.pk)
    return _guardar(request, v, p, None)


@requiere_rol(Rol.TESORERO)
def linea_editar(request: HttpRequest, pk: int, linea_pk: int) -> HttpResponse:
    v = _version_borrador(pk)
    linea = get_object_or_404(Linea.objects.select_related("partida"), pk=linea_pk, version=v)
    if not v.editable or linea.anulada:
        messages.error(request, "Esta línea no se puede modificar.")
        return redirect("presupuesto:version", pk=v.pk)
    return _guardar(request, v, linea.partida, linea)


@requiere_rol(Rol.TESORERO)
def linea_anular(request: HttpRequest, pk: int, linea_pk: int) -> HttpResponse:
    v = _version_borrador(pk)
    linea = get_object_or_404(Linea, pk=linea_pk, version=v)
    form = AnularLineaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            servicios.anular_linea(
                Contexto.desde_request(request), linea, form.cleaned_data["motivo"]
            )
        except (ValidationError, VersionNoEditable) as error:
            form.add_error(None, error if isinstance(error, ValidationError) else str(error))
        else:
            messages.success(request, "Línea anulada (se conserva en el historial).")
            return redirect("presupuesto:version", pk=v.pk)
    return render(
        request, "presupuesto/linea_anular.html", {"version": v, "linea": linea, "form": form}
    )


@requiere_rol(*TODOS)
def configuracion(request: HttpRequest) -> HttpResponse:
    cuadro = cargar_cuadro_cuentas()
    return render(
        request,
        "presupuesto/configuracion.html",
        {
            "cuadro": cuadro,
            "capitulos": Capitulo.objects.filter(activo=True).prefetch_related("partidas__cuentas"),
            "parametros": ParametroLegal.objects.filter(activo=True),
        },
    )
