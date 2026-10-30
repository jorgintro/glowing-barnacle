from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.auditoria.servicios import Contexto
from apps.presupuesto.errores import VersionNoEditable
from apps.presupuesto.models import Ejercicio, VersionPresupuesto
from apps.presupuesto.permisos import versiones_visibles
from apps.usuarios.decoradores import requiere_rol
from apps.usuarios.roles import Rol

from . import servicios
from .campana import construir_plan_campana
from .comparativa import construir_comparativa
from .completitud import textos_de
from .configuracion import asegurar_configuracion, parametros_actuales
from .ejecucion import anular_importacion, importacion_vigente, importar_ejecucion, plantilla_csv
from .forms import (
    ImportarEjecucionForm,
    MotivoAnulacionForm,
    NuevaSeccionForm,
    ParametrosForm,
    ProcesoElectoralForm,
    SaldoInicialForm,
    SeccionCfgForm,
    TextoSeccionForm,
)
from .memoria import construir_memoria, texto_inicial
from .models import (
    ImportacionEjecucion,
    ParametrosAnexosCfg,
    ProcesoElectoral,
    SeccionMemoriaCfg,
)
from .tesoreria import MESES, calcular_plan

TODOS = (Rol.TESORERO, Rol.COMISION_PERMANENTE, Rol.JUNTA_GENERAL)


def _visible(request: HttpRequest, pk: int) -> VersionPresupuesto:
    v = versiones_visibles(request.rol_activo).filter(pk=pk).first()  # type: ignore[attr-defined]
    if v is None:
        raise Http404("Versión no disponible con tu rol.")
    return v


def _errores(request: HttpRequest, error: Exception) -> None:
    if isinstance(error, ValidationError):
        for m in error.messages:
            messages.error(request, m)
    else:
        messages.error(request, str(error))


def _puede_editar(request: HttpRequest, v: VersionPresupuesto) -> bool:
    return request.rol_activo == Rol.TESORERO and v.editable  # type: ignore[attr-defined]


# ----------------------------------------------------------------------- memoria


@requiere_rol(*TODOS)
def memoria(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    return render(
        request,
        "anexos/memoria.html",
        {"version": v, "memoria": construir_memoria(v), "puede_editar": _puede_editar(request, v)},
    )


@requiere_rol(Rol.TESORERO)
def memoria_editar(request: HttpRequest, pk: int, clave: str) -> HttpResponse:
    v = _visible(request, pk)
    cfg = parametros_actuales(v.es_demo).seccion(clave)
    if (
        cfg is None
        or cfg.solo_automatica
        or not cfg.aplicables_a(v.ejercicio.hay_proceso_electoral)
    ):
        raise Http404("Sección no disponible.")
    if not v.editable:
        messages.error(request, "Esta versión es de solo lectura.")
        return redirect("anexos:memoria", pk=v.pk)
    guardada = textos_de(v).get(clave)
    inicial = guardada.texto if guardada and "plantilla" not in request.GET else ""
    usando_plantilla = not inicial.strip()
    if usando_plantilla:
        inicial = texto_inicial(cfg, v)
    form = TextoSeccionForm(request.POST or None, initial={"texto": inicial})
    if request.method == "POST" and form.is_valid():
        try:
            servicios.guardar_seccion(
                Contexto.desde_request(request), v, clave, form.cleaned_data["texto"]
            )
        except (ValidationError, PermissionDenied, VersionNoEditable) as error:
            _errores(request, error)
        else:
            messages.success(request, f"Sección «{cfg.titulo}» guardada.")
            return redirect("anexos:memoria", pk=v.pk)
    return render(
        request,
        "anexos/memoria_editar.html",
        {
            "version": v,
            "cfg": cfg,
            "form": form,
            "usando_plantilla": usando_plantilla,
            "pendiente": bool(guardada and guardada.pendiente_revision),
        },
    )


# ----------------------------------------------------------------------- campaña


@requiere_rol(*TODOS)
def campana(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    if not v.ejercicio.hay_proceso_electoral:
        return render(request, "anexos/campana.html", {"version": v, "sin_proceso": True})
    puede = _puede_editar(request, v)
    form = None
    if puede:
        existente = ProcesoElectoral.objects.filter(version=v).first()
        form = ProcesoElectoralForm(request.POST or None, instance=existente)
        if request.method == "POST" and form.is_valid():
            try:
                servicios.guardar_proceso_electoral(
                    Contexto.desde_request(request),
                    v,
                    **{c: form.cleaned_data[c] for c in form.fields},
                )
            except (ValidationError, PermissionDenied, VersionNoEditable) as error:
                _errores(request, error)
            else:
                messages.success(request, "Datos del proceso electoral guardados.")
                return redirect("anexos:campana", pk=v.pk)
    return render(
        request,
        "anexos/campana.html",
        {
            "version": v,
            "plan": construir_plan_campana(v),
            "form": form,
            "puede_editar": puede,
            "meses": MESES,
        },
    )


# --------------------------------------------------------------------- tesorería


@requiere_rol(*TODOS)
def tesoreria(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    puede = _puede_editar(request, v)
    form = None
    if puede:
        form = SaldoInicialForm(request.POST or None, initial={"saldo": v.saldo_inicial_tesoreria})
        if request.method == "POST" and form.is_valid():
            try:
                servicios.guardar_saldo_inicial(
                    Contexto.desde_request(request), v, form.cleaned_data["saldo"]
                )
            except (ValidationError, PermissionDenied, VersionNoEditable) as error:
                _errores(request, error)
            else:
                messages.success(request, "Saldo inicial guardado.")
                return redirect("anexos:tesoreria", pk=v.pk)
    return render(
        request,
        "anexos/tesoreria.html",
        {"version": v, "plan": calcular_plan(v), "form": form, "puede_editar": puede},
    )


# ----------------------------------------------------------- comparativa y ejecución


@requiere_rol(*TODOS)
def comparativa(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    return render(
        request,
        "anexos/comparativa.html",
        {"version": v, "comp": construir_comparativa(v), "meses": MESES},
    )


@requiere_rol(Rol.TESORERO)
def ejecucion(request: HttpRequest, pk: int) -> HttpResponse:
    ejercicio = get_object_or_404(Ejercicio, pk=pk)
    form = ImportarEjecucionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        fichero = form.cleaned_data["fichero"]
        try:
            imp = importar_ejecucion(
                Contexto.desde_request(request),
                ejercicio,
                nombre_fichero=fichero.name,
                contenido=fichero.read(),
                mes_corte=form.cleaned_data["mes_corte"],
            )
        except (ValidationError, PermissionDenied) as error:
            _errores(request, error)
        else:
            messages.success(
                request, f"Importadas {imp.filas} filas (corte en el mes {imp.mes_corte})."
            )
            return redirect("anexos:ejecucion", pk=ejercicio.pk)
    ultima = ejercicio.versiones.order_by("-numero").first()
    return render(
        request,
        "anexos/ejecucion.html",
        {
            "ejercicio": ejercicio,
            "form": form,
            "form_anular": MotivoAnulacionForm(),
            "importaciones": ejercicio.importaciones.select_related("importado_por"),
            "vigente": importacion_vigente(ejercicio),
            "version_para_comparar": ejercicio.versiones.exclude(estado="BORRADOR")
            .order_by("-numero")
            .first()
            or ultima,
        },
    )


@requiere_rol(Rol.TESORERO)
def ejecucion_plantilla(request: HttpRequest, pk: int) -> HttpResponse:
    ejercicio = get_object_or_404(Ejercicio, pk=pk)
    respuesta = HttpResponse(
        "\ufeff" + plantilla_csv(ejercicio), content_type="text/csv; charset=utf-8"
    )
    respuesta["Content-Disposition"] = (
        f'attachment; filename="plantilla_ejecucion_{ejercicio.anio}.csv"'
    )
    return respuesta


@requiere_rol(Rol.TESORERO)
@require_POST
def ejecucion_anular(request: HttpRequest, pk: int, importacion_pk: int) -> HttpResponse:
    ejercicio = get_object_or_404(Ejercicio, pk=pk)
    imp = get_object_or_404(ImportacionEjecucion, pk=importacion_pk, ejercicio=ejercicio)
    form = MotivoAnulacionForm(request.POST)
    if form.is_valid():
        try:
            anular_importacion(Contexto.desde_request(request), imp, form.cleaned_data["motivo"])
        except (ValidationError, PermissionDenied) as error:
            _errores(request, error)
        else:
            messages.success(request, "Importación anulada. La comparativa usa la anterior activa.")
    else:
        messages.error(request, "Anular una importación exige un motivo.")
    return redirect("anexos:ejecucion", pk=ejercicio.pk)


# ------------------------------------------------------- panel de configuración


def _demo(request: HttpRequest) -> bool:
    return bool(getattr(request.user, "es_demo", False))


def _valores_parametros(p: ParametrosAnexosCfg) -> dict[str, Any]:
    return {
        "variaciones_destacadas": p.variaciones_destacadas,
        "marcas_pendiente": p.marcas_pendiente,
        "saldo_minimo_tesoreria": p.saldo_minimo_tesoreria,
        "porcentaje_aviso_limite_campana": p.porcentaje_aviso_limite_campana,
        "semaforo_ambar_pct": p.semaforo_ambar_pct,
        "semaforo_rojo_pct": p.semaforo_rojo_pct,
        "semaforo_importe_minimo": p.semaforo_importe_minimo,
        "reduccion_ingresos_alta": p.reduccion_ingresos_alta,
        "reduccion_ingresos_media": p.reduccion_ingresos_media,
        "reduccion_ingresos_baja": p.reduccion_ingresos_baja,
        "reduccion_gastos_recurrente": p.reduccion_gastos_recurrente,
        "reduccion_gastos_extraordinario": p.reduccion_gastos_extraordinario,
        "reduccion_gastos_condicionado": p.reduccion_gastos_condicionado,
    }


@requiere_rol(Rol.TESORERO)
def configuracion(request: HttpRequest) -> HttpResponse:
    demo = _demo(request)
    asegurar_configuracion(demo)
    p = ParametrosAnexosCfg.objects.get(es_demo=demo)
    form = ParametrosForm(request.POST or None, initial=_valores_parametros(p))
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            servicios.guardar_parametros(
                Contexto.desde_request(request),
                demo=demo,
                variaciones_destacadas=d["variaciones_destacadas"],
                marcas_pendiente=d["marcas_pendiente"],
                saldo_minimo_tesoreria=d["saldo_minimo_tesoreria"],
                porcentaje_aviso_limite_campana=d["porcentaje_aviso_limite_campana"],
                semaforo_ambar_pct=d["semaforo_ambar_pct"],
                semaforo_rojo_pct=d["semaforo_rojo_pct"],
                semaforo_importe_minimo=d["semaforo_importe_minimo"],
                **{c: d[c] for c in d if c.startswith("reduccion_")},
            )
        except (ValidationError, PermissionDenied) as error:
            _errores(request, error)
        else:
            messages.success(request, "Parámetros guardados.")
            return redirect("anexos:configuracion")
    return render(
        request,
        "anexos/configuracion.html",
        {
            "form": form,
            "secciones": SeccionMemoriaCfg.objects.filter(es_demo=demo),
            "form_nueva": NuevaSeccionForm(),
            "demo": demo,
        },
    )


@requiere_rol(Rol.TESORERO)
def seccion_cfg_editar(request: HttpRequest, pk: int) -> HttpResponse:
    cfg = get_object_or_404(SeccionMemoriaCfg, pk=pk, es_demo=_demo(request))
    form = SeccionCfgForm(request.POST or None, instance=cfg)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            servicios.guardar_seccion_cfg(
                Contexto.desde_request(request),
                cfg,
                titulo=d["titulo"],
                orden=d["orden"],
                obligatoria=d["obligatoria"],
                activa=d["activa"],
                longitud_minima=d["longitud_minima"],
                solo_con_proceso_electoral=d["solo_con_proceso_electoral"],
                ayuda=d["ayuda"],
                plantilla=d["plantilla"],
            )
        except (ValidationError, PermissionDenied) as error:
            _errores(request, error)
        else:
            messages.success(request, "Sección guardada.")
            return redirect("anexos:configuracion")
    return render(request, "anexos/seccion_cfg.html", {"form": form, "cfg": cfg})


@requiere_rol(Rol.TESORERO)
@require_POST
def seccion_cfg_nueva(request: HttpRequest) -> HttpResponse:
    form = NuevaSeccionForm(request.POST)
    if form.is_valid():
        try:
            cfg = servicios.crear_seccion_cfg(
                Contexto.desde_request(request),
                titulo=form.cleaned_data["titulo"],
                demo=_demo(request),
            )
        except (ValidationError, PermissionDenied) as error:
            _errores(request, error)
        else:
            messages.success(request, "Sección añadida. Ajusta ahora sus detalles.")
            return redirect("anexos:seccion_cfg", pk=cfg.pk)
    else:
        messages.error(request, "Escribe el título de la sección nueva.")
    return redirect("anexos:configuracion")


@requiere_rol(Rol.TESORERO)
@require_POST
def seccion_cfg_restablecer(request: HttpRequest, pk: int) -> HttpResponse:
    cfg = get_object_or_404(SeccionMemoriaCfg, pk=pk, es_demo=_demo(request))
    try:
        servicios.restablecer_seccion_cfg(Contexto.desde_request(request), cfg)
    except (ValidationError, PermissionDenied) as error:
        _errores(request, error)
    else:
        messages.success(request, "Ayuda, plantilla y exigencias vueltas a los valores propuestos.")
    return redirect("anexos:seccion_cfg", pk=cfg.pk)
