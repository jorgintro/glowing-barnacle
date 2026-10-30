from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.auditoria.servicios import Contexto
from apps.flujo.panel import contexto_flujo
from apps.flujo.servicios import prorroga_disponible as flujo_prorroga
from apps.usuarios.decoradores import requiere_rol
from apps.usuarios.roles import Rol
from apps.validaciones.motor import CATALOGO, validar_version

from . import donantes as dn
from . import servicios
from .calculos import resumen_version
from .configuracion import cargar_cuadro_cuentas
from .errores import VersionNoEditable
from .forms import (
    MESES,
    AnularDonacionForm,
    AnularLineaForm,
    BajaDonanteForm,
    DonacionForm,
    DonanteForm,
    EjercicioForm,
    LineaForm,
    ResultadoForm,
)
from .models import (
    Ambito,
    Capitulo,
    Donacion,
    Donante,
    Ejercicio,
    Linea,
    ParametroLegal,
    Partida,
    VersionPresupuesto,
)
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
    es_tesorero = request.rol_activo == Rol.TESORERO  # type: ignore[attr-defined]
    filas = [
        {
            "ejercicio": e,
            "versiones": por_ejercicio[e.pk],
            "ordinarias": [v for v in por_ejercicio[e.pk] if v.ambito == Ambito.ORDINARIO],
            "electorales": [v for v in por_ejercicio[e.pk] if v.ambito == Ambito.ELECTORAL],
            "puede_crear_electoral": es_tesorero
            and e.hay_proceso_electoral
            and not e.versiones.filter(ambito=Ambito.ELECTORAL).exists(),
            "prorroga": flujo_prorroga(e) if es_tesorero else (False, ""),
        }
        for e in ejercicios
    ]
    sin_versiones = []
    if request.rol_activo == Rol.TESORERO:  # type: ignore[attr-defined]
        sin_versiones = list(Ejercicio.objects.exclude(pk__in=por_ejercicio))
    return render(request, "presupuesto/lista.html", {"filas": filas, "vacios": sin_versiones})


@requiere_rol(Rol.TESORERO)
@require_POST
def crear_electoral(request: HttpRequest, pk: int) -> HttpResponse:
    ejercicio = get_object_or_404(Ejercicio, pk=pk)
    try:
        version = servicios.crear_presupuesto_electoral(Contexto.desde_request(request), ejercicio)
    except ValidationError as error:
        for m in error.messages:
            messages.error(request, m)
        return redirect("presupuesto:lista")
    messages.success(request, "Presupuesto electoral creado, con su propio flujo.")
    return redirect("presupuesto:version", pk=version.pk)


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
            if version.ejercicio.hay_proceso_electoral:
                servicios.crear_presupuesto_electoral(
                    Contexto.desde_request(request), version.ejercicio
                )
                messages.success(
                    request,
                    "Ejercicio creado con su borrador ordinario y su presupuesto electoral, "
                    "que tiene un flujo propio y separado.",
                )
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
        if t.capitulo.ambito == v.ambito
    ]
    puede_editar = request.rol_activo == Rol.TESORERO and v.editable  # type: ignore[attr-defined]
    validacion = validar_version(v)
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
            "validacion": validacion,
            "con_donantes": dn.CAPITULOS_CON_DONANTES,
            "flujo": contexto_flujo(request, v),
            "otras_versiones": v.ejercicio.versiones.filter(ambito=v.ambito).exclude(pk=v.pk),
        },
    )


@requiere_rol(Rol.TESORERO)
def linea_elegir_partida(request: HttpRequest, pk: int) -> HttpResponse:
    v = _version_borrador(pk)
    if not v.editable:
        messages.error(request, "Esta versión es de solo lectura.")
        return redirect("presupuesto:version", pk=v.pk)
    capitulos = Capitulo.objects.filter(activo=True, ambito=v.ambito).prefetch_related("partidas")
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
                origen_ingreso=d.get("origen_ingreso", ""),
                operaciones_altas=d.get("operaciones_altas"),
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


# ------------------------------------------------------------------- validaciones


@requiere_rol(*TODOS)
def validaciones(request: HttpRequest, pk: int) -> HttpResponse:
    v = _version_visible(request, pk)
    resultado = validar_version(v)
    por_regla = []
    for regla in CATALOGO:
        incidencias = [i for i in resultado.incidencias if i.codigo == regla.codigo]
        por_regla.append({"regla": regla, "incidencias": incidencias, "ok": not incidencias})
    return render(
        request,
        "presupuesto/validaciones.html",
        {"version": v, "resultado": resultado, "por_regla": por_regla, "usa_demo": v.es_demo},
    )


@requiere_rol(Rol.TESORERO)
def resultado(request: HttpRequest, pk: int) -> HttpResponse:
    v = _version_borrador(pk)
    if not v.editable:
        messages.error(request, "Esta versión es de solo lectura.")
        return redirect("presupuesto:version", pk=v.pk)
    inicial = {
        "explicacion": v.explicacion_resultado,
        "plan_financiacion": v.plan_financiacion,
        "endeudamiento": v.endeudamiento_previsto,
    }
    form = ResultadoForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        try:
            dn.guardar_resultado(Contexto.desde_request(request), v, **form.cleaned_data)
        except (ValidationError, VersionNoEditable) as error:
            form.add_error(None, error if isinstance(error, ValidationError) else str(error))
        else:
            messages.success(request, "Resultado guardado.")
            return redirect("presupuesto:version", pk=v.pk)
    return render(request, "presupuesto/resultado.html", {"version": v, "form": form})


# ---------------------------------------------------------------------- donantes


@requiere_rol(Rol.TESORERO)
def donantes_lista(request: HttpRequest) -> HttpResponse:
    form = DonanteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            dn.crear_donante(Contexto.desde_request(request), **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Donante registrado.")
            return redirect("presupuesto:donantes")
    return render(
        request,
        "presupuesto/donantes.html",
        {"form": form, "donantes": Donante.objects.order_by("-activo", "nombre")},
    )


@requiere_rol(Rol.TESORERO)
def donante_baja(request: HttpRequest, pk: int) -> HttpResponse:
    donante = get_object_or_404(Donante, pk=pk)
    form = BajaDonanteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            dn.dar_de_baja_donante(
                Contexto.desde_request(request), donante, form.cleaned_data["motivo"]
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Donante dado de baja (se conserva en el historial).")
            return redirect("presupuesto:donantes")
    return render(request, "presupuesto/donante_baja.html", {"donante": donante, "form": form})


@requiere_rol(Rol.TESORERO)
def linea_donaciones(request: HttpRequest, pk: int, linea_pk: int) -> HttpResponse:
    v = _version_borrador(pk)
    linea = get_object_or_404(
        Linea.objects.select_related("partida__capitulo"), pk=linea_pk, version=v
    )
    if linea.partida.capitulo.codigo not in dn.CAPITULOS_CON_DONANTES:
        messages.error(request, "Esta línea no admite donantes.")
        return redirect("presupuesto:version", pk=v.pk)
    form = DonacionForm(request.POST or None, es_demo=v.es_demo)
    if request.method == "POST" and v.editable and form.is_valid():
        try:
            dn.registrar_donacion(
                Contexto.desde_request(request),
                v,
                linea,
                form.cleaned_data["donante"],
                form.cleaned_data["importe"],
                tipo=form.cleaned_data["tipo"],
                finalista=form.cleaned_data["finalista"],
                revocable=form.cleaned_data["revocable"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Donación registrada.")
            return redirect("presupuesto:linea_donaciones", pk=v.pk, linea_pk=linea.pk)
    donaciones = Donacion.objects.filter(linea=linea).select_related("donante").order_by("creada")
    identificado = sum((d.importe for d in donaciones if not d.anulada), Decimal("0.00"))
    return render(
        request,
        "presupuesto/linea_donaciones.html",
        {
            "version": v,
            "linea": linea,
            "form": form,
            "donaciones": donaciones,
            "identificado": identificado,
            "sin_identificar": linea.importe_anual - identificado,
            "acumulado": dn.acumulado_anual(v),
            "puede_editar": v.editable,
        },
    )


@requiere_rol(Rol.TESORERO)
def donacion_anular(request: HttpRequest, pk: int, donacion_pk: int) -> HttpResponse:
    v = _version_borrador(pk)
    donacion = get_object_or_404(
        Donacion.objects.select_related("donante", "linea"), pk=donacion_pk, version=v
    )
    form = AnularDonacionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            dn.anular_donacion(
                Contexto.desde_request(request), donacion, form.cleaned_data["motivo"]
            )
        except (ValidationError, VersionNoEditable) as error:
            form.add_error(None, error if isinstance(error, ValidationError) else str(error))
        else:
            messages.success(request, "Donación anulada (se conserva en el historial).")
            return redirect("presupuesto:linea_donaciones", pk=v.pk, linea_pk=donacion.linea_id)
    return render(
        request,
        "presupuesto/donacion_anular.html",
        {"version": v, "donacion": donacion, "form": form},
    )
