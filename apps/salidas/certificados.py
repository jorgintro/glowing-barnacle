"""Certificados de aprobación (HTML y PDF).

Excepción expresa a la regla general de «solo Excel y HTML» (CLAUDE.md §11): el Tesorero pidió
que los certificados se generen también en PDF. Es lo único del sistema que genera PDF.

Un certificado no es una firma electrónica: lleva líneas de firma para firmarlo a mano.
"""

import io
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone

from apps.flujo.models import EstadoVotacion, ResultadoRatificacion, ResultadoVotacion, Votacion
from apps.flujo.panel import nombre_miembro  # noqa: F401  (reexportado para las vistas)
from apps.flujo.sello import verificar_integridad
from apps.organizacion.models import Organizacion, Persona
from apps.presupuesto.calculos import resumen_version
from apps.presupuesto.dinero import formatear_euros
from apps.presupuesto.models import VersionPresupuesto
from apps.usuarios.models import Usuario

TIPOS = {
    "CP": "Aprobación por la Comisión Permanente",
    "JG": "Ratificación por la Junta General",
}


@dataclass
class DatosCertificado:
    tipo: str
    titulo: str
    organizacion: Organizacion
    version: VersionPresupuesto
    firmante: Persona
    visto_bueno: Persona | None
    fecha_emision: date
    parrafos: list[str]
    cifras: list[tuple[str, str]]
    asistentes: list[tuple[str, str]] = field(default_factory=list)
    votos: list[tuple[str, str]] | None = None
    observaciones: str = ""
    es_demo: bool = False

    @property
    def huella(self) -> str:
        return self.version.hash

    @property
    def nombre_fichero(self) -> str:
        v = self.version
        return f"certificado_{self.tipo.lower()}_{v.ejercicio.anio}_v{v.numero}"


def _fecha(d: date) -> str:
    return f"{d:%d/%m/%Y}"


def _persona_de(usuario: Usuario) -> tuple[str, str]:
    p = Persona.objects.filter(usuario=usuario).first()
    if p is None:
        return usuario.nombre_visible(), "—"
    return p.nombre_completo, p.cargos_texto() or "—"


def _identificacion(p: Persona) -> str:
    return f"{p.nombre_completo}, con DNI {p.dni}, en calidad de {p.cargos_texto()}"


def construir_certificado(
    version: VersionPresupuesto,
    tipo: str,
    firmante: Persona,
    visto_bueno: Persona | None = None,
    *,
    incluir_votos: bool = False,
    hoy: date | None = None,
) -> DatosCertificado:
    """Reúne los datos del certificado. Falla si la versión no está aprobada o fue manipulada."""
    if tipo not in TIPOS:
        raise ValidationError("Tipo de certificado desconocido.")
    for persona, nombre in ((firmante, "firmante"), (visto_bueno, "persona del visto bueno")):
        if persona is None:
            continue
        if not persona.activa:
            raise ValidationError(f"La {nombre} está de baja.")
        if not persona.cargos.filter(activo=True).exists():
            raise ValidationError(
                f"La {nombre} ({persona.nombre_completo}) no tiene ningún cargo en el panel."
            )
    integridad = verificar_integridad(version)
    if not integridad.ok:
        raise ValidationError(
            "No se emite certificado de una versión cuya integridad falla: "
            + " ".join(integridad.problemas)
        )
    org = Organizacion.obtener()
    hoy = hoy or timezone.localdate()
    ej = version.ejercicio
    res = resumen_version(version)
    cifras = [
        ("Ingresos previstos", formatear_euros(res.ingresos)),
        ("Gastos previstos", formatear_euros(res.gastos)),
        (
            "Resultado presupuestario (" + ("déficit" if res.es_deficit else "superávit") + ")",
            formatear_euros(res.resultado),
        ),
    ]
    nombre_presupuesto = "presupuesto electoral" if version.es_electoral else "presupuesto"
    sujeto = (
        f"el {nombre_presupuesto} del ejercicio {ej.anio}, versión {version.numero}"
        + (" (prórroga provisional)" if version.es_prorroga else "")
        + (" (modificación presupuestaria)" if version.tipo_origen == "MODIFICACION" else "")
    )
    base = f"{_identificacion(firmante)}, CERTIFICA:"
    asistentes: list[tuple[str, str]] = []
    votos: list[tuple[str, str]] | None = None
    observaciones = ""

    if tipo == "CP":
        vot = (
            Votacion.objects.filter(
                version=version,
                estado=EstadoVotacion.CERRADA,
                resultado=ResultadoVotacion.APROBADA,
            )
            .order_by("-id")
            .first()
        )
        if vot is None:
            raise ValidationError(
                "Esta versión no tiene una votación aprobada de la Comisión Permanente."
            )
        assert vot.cerrada_en is not None
        fecha = timezone.localtime(vot.cerrada_en).date()
        ordenados = vot.votos.select_related("usuario").order_by("emitido_en")
        asistentes = [_persona_de(v.usuario) for v in ordenados]
        if incluir_votos:
            votos = [(_persona_de(v.usuario)[0], v.get_voto_display()) for v in ordenados]
        observaciones = vot.observaciones
        parrafos = [
            base,
            f"Que {sujeto}, propuesto por el cargo de {org.denominacion_tesoreria}, fue "
            f"APROBADO por la Comisión Permanente de {org.nombre} en votación cerrada el "
            f"{_fecha(fecha)}.",
            f"Asistieron {vot.asistentes} de {vot.miembros} miembros. Votos a favor: "
            f"{vot.a_favor}; en contra: {vot.en_contra}; abstenciones: {vot.abstenciones}. "
            "Hubo quórum y mayoría conforme a las reglas orgánicas aplicadas por el sistema.",
        ]
        if version.estado == "MODIFICADO":
            parrafos.append(
                "La modificación no superaba el umbral que obliga a una nueva ratificación de la "
                "Junta General, por lo que es definitiva con esta aprobación."
            )
        elif version.requiere_junta:
            parrafos.append("Queda pendiente su ratificación por la Junta General.")
        titulo = f"Certificado de aprobación del {nombre_presupuesto} por la Comisión Permanente"
    else:
        rat = getattr(version, "ratificacion", None)
        if rat is None or rat.resultado != ResultadoRatificacion.RATIFICADO:
            raise ValidationError("Esta versión no está ratificada por la Junta General.")
        observaciones = rat.observaciones
        parrafos = [
            base,
            f"Que {sujeto} fue RATIFICADO por la Junta General de {org.nombre} en la sesión "
            f"celebrada el {_fecha(rat.fecha_sesion)}, según consta en el acta: "
            f"{rat.referencia_acta}.",
        ]
        if rat.convocatoria is not None:
            c = rat.convocatoria
            parrafos.append(f"La Junta fue convocada el {_fecha(c.fecha_convocatoria)}.")
        parrafos.append(
            "El presupuesto había sido aprobado previamente por la Comisión Permanente "
            "conforme a los estatutos y reglamentos de la organización."
        )
        titulo = f"Certificado de ratificación del {nombre_presupuesto} por la Junta General"

    parrafos.append(
        f"Y para que conste, se expide el presente certificado en {org.localidad}, a {_fecha(hoy)}."
    )
    return DatosCertificado(
        tipo=tipo,
        titulo=titulo,
        organizacion=org,
        version=version,
        firmante=firmante,
        visto_bueno=visto_bueno,
        fecha_emision=hoy,
        parrafos=parrafos,
        cifras=cifras,
        asistentes=asistentes,
        votos=votos,
        observaciones=observaciones,
        es_demo=version.es_demo,
    )


AVISO_DEMO = "DATOS FICTICIOS DE DEMOSTRACIÓN · SIN VALIDEZ"
NOTA_PIE = (
    "Documento generado por el sistema. No es una firma electrónica: debe firmarse a mano. "
    "La huella identifica el contenido exacto de la versión certificada."
)


def certificado_html(datos: DatosCertificado) -> str:
    """Documento autónomo (estilos incrustados), imprimible desde el navegador."""
    return render_to_string(
        "salidas/certificado.html",
        {"d": datos, "aviso_demo": AVISO_DEMO, "nota_pie": NOTA_PIE},
    )


def certificado_pdf(datos: DatosCertificado) -> bytes:
    """El mismo certificado en PDF (reportlab)."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    marca = colors.HexColor("#14284b")
    gris = colors.HexColor("#5b6478")
    cuerpo = ParagraphStyle(
        "cuerpo",
        fontName="Times-Roman",
        fontSize=11.5,
        leading=17,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
    )
    titulo = ParagraphStyle(
        "titulo",
        fontName="Times-Bold",
        fontSize=17,
        leading=21,
        alignment=TA_CENTER,
        textColor=marca,
        spaceAfter=6,
    )
    sub = ParagraphStyle(
        "sub",
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=gris,
        spaceAfter=14,
    )
    h2 = ParagraphStyle(
        "h2",
        fontName="Times-Bold",
        fontSize=12,
        leading=15,
        textColor=marca,
        spaceBefore=10,
        spaceAfter=5,
    )
    peq = ParagraphStyle("peq", fontName="Helvetica", fontSize=8, leading=10.5, textColor=gris)
    mono = ParagraphStyle(
        "mono", fontName="Courier", fontSize=8, leading=10, textColor=colors.black
    )
    centro = ParagraphStyle("centro", parent=cuerpo, alignment=TA_CENTER, spaceAfter=0)

    def p(texto: str, estilo: ParagraphStyle) -> Paragraph:
        return Paragraph(escape(texto), estilo)

    v = datos.version
    org = datos.organizacion
    historia: list[Any] = [
        p(org.nombre.upper(), sub),
        p(datos.titulo, titulo),
        p(f"Ejercicio {v.ejercicio.anio} · versión {v.numero} · {v.get_estado_display()}", sub),
    ]
    for texto in datos.parrafos:
        historia.append(p(texto, cuerpo))

    def tabla(filas: list[list[str]], anchos: list[float], cabecera: bool = False) -> Table:
        t = Table(
            [
                [
                    Paragraph(
                        escape(c),
                        ParagraphStyle("c", fontName="Helvetica", fontSize=9.5, leading=12),
                    )
                    for c in f
                ]
                for f in filas
            ],
            colWidths=anchos,
        )
        estilo = [
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9dbe2")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f4f5f8")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if cabecera:
            estilo.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecf4")))
        t.setStyle(TableStyle(estilo))
        return t

    historia.append(p("Cifras del presupuesto certificado", h2))
    historia.append(tabla([[a, b] for a, b in datos.cifras], [10.5 * cm, 5.5 * cm]))
    if datos.asistentes:
        historia.append(p("Miembros que participaron en la votación", h2))
        historia.append(
            tabla(
                [["Nombre", "Cargo"], *[[n, c] for n, c in datos.asistentes]],
                [8.5 * cm, 7.5 * cm],
                cabecera=True,
            )
        )
    if datos.votos is not None:
        historia.append(p("Voto de cada miembro", h2))
        historia.append(
            tabla(
                [["Miembro", "Voto"], *[[n, x] for n, x in datos.votos]],
                [10.5 * cm, 5.5 * cm],
                cabecera=True,
            )
        )
    if datos.observaciones:
        historia.append(p("Observaciones", h2))
        historia.append(p(datos.observaciones, cuerpo))

    historia.append(Spacer(1, 1.6 * cm))
    firmas = [datos.firmante] + ([datos.visto_bueno] if datos.visto_bueno else [])
    fila_firma = []
    for i, persona in enumerate(firmas):
        etiqueta = "El/La firmante" if i == 0 else "Vº Bº"
        fila_firma.append(
            [
                p(etiqueta, ParagraphStyle("e", parent=peq, alignment=TA_CENTER)),
                Spacer(1, 1.6 * cm),
                p("_" * 34, centro),
                p(persona.nombre_completo, centro),
                p(f"DNI {persona.dni}", ParagraphStyle("d", parent=peq, alignment=TA_CENTER)),
                p(persona.cargos_texto(), ParagraphStyle("d2", parent=peq, alignment=TA_CENTER)),
            ]
        )
    historia.append(Table([fila_firma], colWidths=[16.0 * cm / len(firmas)] * len(firmas)))
    historia.append(Spacer(1, 0.8 * cm))
    historia.append(p("Huella (SHA-256) de la versión certificada:", peq))
    historia.append(
        Paragraph(escape(datos.huella[:32]) + "<br/>" + escape(datos.huella[32:]), mono)
    )
    historia.append(Spacer(1, 4))
    historia.append(p(NOTA_PIE, peq))

    def marca_agua(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        if datos.es_demo:
            canvas.setFillColor(colors.Color(0.8, 0.1, 0.1, alpha=0.16))
            canvas.setFont("Helvetica-Bold", 30)
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 20, "DATOS FICTICIOS DE DEMOSTRACIÓN")
            canvas.drawCentredString(0, -20, "SIN VALIDEZ")
        canvas.restoreState()
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(gris)
        canvas.drawString(
            2 * cm, 1.2 * cm, f"{org.nombre} · Certificado emitido el {_fecha(datos.fecha_emision)}"
        )
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2.2 * cm,
        title=datos.titulo,
        author=org.nombre,
        pageCompression=0,  # PDF pequeño y con texto buscable (también facilita las pruebas)
        invariant=True,
    )
    doc.build(historia, onFirstPage=marca_agua, onLaterPages=marca_agua)
    return buffer.getvalue()
