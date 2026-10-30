from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from apps.auditoria.servicios import Contexto, registrar
from apps.flujo.models import ResultadoRatificacion
from apps.organizacion.models import Persona
from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import VersionPresupuesto
from apps.presupuesto.permisos import versiones_visibles
from apps.usuarios.decoradores import requiere_rol
from apps.usuarios.roles import Rol

from .certificados import certificado_html, certificado_pdf, construir_certificado
from .forms import CertificadoForm

TODOS = (Rol.TESORERO, Rol.COMISION_PERMANENTE, Rol.JUNTA_GENERAL)


def _visible(request: HttpRequest, pk: int) -> VersionPresupuesto:
    v = versiones_visibles(request.rol_activo).filter(pk=pk).first()  # type: ignore[attr-defined]
    if v is None:
        raise Http404("Versión no disponible con tu rol.")
    return v


def _tipos_disponibles(v: VersionPresupuesto) -> list[str]:
    tipos = []
    if v.estado in (
        EstadoVersion.APROBADO_CP,
        EstadoVersion.RATIFICADO_JG,
        EstadoVersion.MODIFICADO,
    ):
        tipos.append("CP")
    rat = getattr(v, "ratificacion", None)
    if (
        v.estado == EstadoVersion.RATIFICADO_JG
        and rat
        and rat.resultado == ResultadoRatificacion.RATIFICADO
    ):
        tipos.append("JG")
    return tipos


@requiere_rol(*TODOS)
def certificados(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    tipos = _tipos_disponibles(v)
    form = CertificadoForm(tipos=tipos, es_demo=v.es_demo)
    hay_personas = Persona.objects.filter(
        activa=True, es_demo=v.es_demo, cargos__activo=True
    ).exists()
    return render(
        request,
        "salidas/certificados.html",
        {"version": v, "form": form, "tipos": tipos, "hay_personas": hay_personas},
    )


@requiere_rol(*TODOS)
def certificado(request: HttpRequest, pk: int) -> HttpResponse:
    v = _visible(request, pk)
    form = CertificadoForm(request.GET, tipos=_tipos_disponibles(v), es_demo=v.es_demo)
    formato = request.GET.get("formato", "html")
    if formato not in ("html", "pdf") or not form.is_valid():
        messages.error(request, "Elige qué certificado quieres, quién lo firma y el formato.")
        return redirect("salidas:certificados", pk=v.pk)
    d = form.cleaned_data
    try:
        datos = construir_certificado(
            v, d["tipo"], d["firmante"], d["visto_bueno"], incluir_votos=d["incluir_votos"]
        )
    except ValidationError as error:
        for m in error.messages:
            messages.error(request, m)
        return redirect("salidas:certificados", pk=v.pk)
    registrar(
        Contexto.desde_request(request),
        accion="certificado.generar",
        entidad="VersionPresupuesto",
        entidad_id=v.pk,
        despues={
            "tipo": d["tipo"],
            "formato": formato,
            "firmante_id": d["firmante"].pk,
            "visto_bueno_id": d["visto_bueno"].pk if d["visto_bueno"] else None,
            "huella": v.hash,
        },
        es_demo=v.es_demo,
    )
    if formato == "pdf":
        respuesta = HttpResponse(certificado_pdf(datos), content_type="application/pdf")
        respuesta["Content-Disposition"] = f'attachment; filename="{datos.nombre_fichero}.pdf"'
        return respuesta
    return HttpResponse(certificado_html(datos))
