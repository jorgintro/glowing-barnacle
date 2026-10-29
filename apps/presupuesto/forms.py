import re
from decimal import Decimal
from typing import Any

from django import forms

from .models import (
    Confianza,
    CuentaPGC,
    Dimension,
    Donante,
    Linea,
    Partida,
    Tipo,
    TipoLinea,
    TipoPersona,
)

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


class EjercicioForm(forms.Form):
    anio = forms.IntegerField(label="Año", min_value=2000, max_value=2100)
    nombre = forms.CharField(label="Nombre (opcional)", max_length=120, required=False)
    hay_proceso_electoral = forms.BooleanField(
        label="Hay proceso electoral previsto en este ejercicio",
        required=False,
        help_text="Activa el capítulo G.7 (gastos electorales) y el anexo de campaña.",
    )


_IMPORTE = re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+)(,\d{1,2})?$")


class ImporteField(forms.DecimalField):
    """Importe en formato español, estricto: ``1.234,56`` o ``1234,56``.

    No se admite el punto como separador decimal («12.50»), porque podría leerse como 1.250 en
    silencio. Ante la duda, se rechaza con un mensaje claro.
    """

    def to_python(self, value: Any) -> Any:
        if value in self.empty_values:
            return None
        texto = str(value).strip().replace("\u00a0", "").replace(" ", "").replace("€", "")
        if not _IMPORTE.match(texto):
            raise forms.ValidationError(
                "Escribe el importe con coma decimal, por ejemplo 1.234,56 o 1234,56.",
                code="invalid",
            )
        return super().to_python(texto.replace(".", "").replace(",", "."))

    def prepare_value(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return f"{value:.2f}".replace(".", ",")
        return value


def _dinero(etiqueta: str, **kw: Any) -> ImporteField:
    return ImporteField(
        label=etiqueta,
        max_digits=14,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "class": "importe"}),
        **kw,
    )


class LineaForm(forms.Form):
    REPARTO = [
        ("UNIFORME", "Repartir por igual entre los 12 meses"),
        ("MANUAL", "Indicar cada mes"),
    ]

    denominacion = forms.CharField(label="Denominación", max_length=200)
    cuenta = forms.ModelChoiceField(label="Cuenta del PGC", queryset=CuentaPGC.objects.none())
    importe_anual = _dinero("Importe anual (€)")
    tipo = forms.ChoiceField(label="Tipo", choices=TipoLinea.choices)
    dimension = forms.ChoiceField(label="Dimensión", choices=Dimension.choices)
    responsable = forms.CharField(label="Responsable (persona o área)", max_length=120)
    hipotesis_texto = forms.CharField(
        label="Hipótesis",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Explica de dónde sale la cifra. No puede quedar vacía.",
    )
    hipotesis_fuente = forms.CharField(
        label="Fuente", max_length=300, help_text="Documento, histórico, contrato, resolución…"
    )
    confianza = forms.ChoiceField(
        label="Confianza en la estimación", choices=[("", "—"), *Confianza.choices], required=False
    )
    importe_anterior = _dinero("Importe del ejercicio anterior (€)", required=False)
    justificacion_variacion = forms.CharField(
        label="Justificación de la variación respecto al ejercicio anterior",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    origen_ingreso = forms.CharField(
        label="Origen del ingreso (opcional)",
        max_length=80,
        required=False,
        help_text="Tipo de fuente; se contrasta con las fuentes de ingreso prohibidas.",
    )
    es_ajuste = forms.BooleanField(label="Es un ajuste (admite importe negativo)", required=False)
    justificacion_ajuste = forms.CharField(
        label="Justificación del ajuste", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    reparto = forms.ChoiceField(
        label="Distribución mensual", choices=REPARTO, widget=forms.RadioSelect, initial="UNIFORME"
    )

    def __init__(self, *args: Any, partida: Partida, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.partida = partida
        self.fields["cuenta"].queryset = partida.cuentas.filter(activa=True)  # type: ignore[attr-defined]
        self.fields["dimension"].initial = partida.dimension_por_defecto
        if partida.capitulo.tipo != Tipo.INGRESO:
            del self.fields["origen_ingreso"]
        for i, mes in enumerate(MESES, start=1):
            self.fields[f"mes_{i}"] = _dinero(mes, required=False)

    def clean(self) -> dict[str, Any]:
        datos = super().clean() or {}
        if self.partida.capitulo.tipo == Tipo.INGRESO and not datos.get("confianza"):
            self.add_error("confianza", "Indica la confianza en la estimación del ingreso.")
        if datos.get("reparto") == "MANUAL":
            vacios = [m for i, m in enumerate(MESES, start=1) if datos.get(f"mes_{i}") is None]
            if vacios and not any(self.has_error(f"mes_{i}") for i in range(1, 13)):
                self.add_error(None, f"Faltan importes de: {', '.join(vacios)}.")
        return datos

    def mensual(self) -> list[Decimal] | None:
        if self.cleaned_data.get("reparto") != "MANUAL":
            return None
        return [self.cleaned_data[f"mes_{i}"] for i in range(1, 13)]

    def campos_mensuales(self) -> list[forms.BoundField]:
        return [self[f"mes_{i}"] for i in range(1, 13)]

    @classmethod
    def inicial_desde(cls, linea: Linea) -> dict[str, Any]:
        h = getattr(linea, "hipotesis", None)
        mensuales = list(linea.importes_mensuales.order_by("mes").values_list("importe", flat=True))
        inicial: dict[str, Any] = {
            "denominacion": linea.denominacion,
            "cuenta": linea.cuenta_pgc_id,
            "importe_anual": linea.importe_anual,
            "tipo": linea.tipo,
            "dimension": linea.dimension,
            "responsable": linea.responsable,
            "hipotesis_texto": h.texto if h else "",
            "hipotesis_fuente": h.fuente if h else "",
            "confianza": h.confianza if h else "",
            "importe_anterior": linea.importe_ejercicio_anterior,
            "justificacion_variacion": linea.justificacion_variacion,
            "es_ajuste": linea.es_ajuste,
            "justificacion_ajuste": linea.justificacion_ajuste,
            "origen_ingreso": linea.origen_ingreso,
            "reparto": "MANUAL",
        }
        for i, importe in enumerate(mensuales, start=1):
            inicial[f"mes_{i}"] = importe
        return inicial


class AnularLineaForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo de la anulación", widget=forms.Textarea(attrs={"rows": 2})
    )


class DonanteForm(forms.Form):
    nombre = forms.CharField(label="Nombre y apellidos o razón social", max_length=200)
    nif = forms.CharField(label="NIF / NIE / CIF", max_length=15)
    tipo_persona = forms.ChoiceField(
        label="Tipo de persona", choices=TipoPersona.choices, initial=TipoPersona.FISICA
    )


class BajaDonanteForm(forms.Form):
    motivo = forms.CharField(label="Motivo de la baja", widget=forms.Textarea(attrs={"rows": 2}))


class DonacionForm(forms.Form):
    donante = forms.ModelChoiceField(label="Donante", queryset=Donante.objects.none())
    importe = _dinero("Importe previsto (€)")

    def __init__(self, *args: Any, es_demo: bool, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        campo = self.fields["donante"]
        assert isinstance(campo, forms.ModelChoiceField)
        campo.queryset = Donante.objects.filter(activo=True, es_demo=es_demo)


class AnularDonacionForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo de la anulación", widget=forms.Textarea(attrs={"rows": 2})
    )


class ResultadoForm(forms.Form):
    explicacion = forms.CharField(
        label="Explicación del resultado presupuestario",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Obligatoria siempre (regla V-006).",
    )
    plan_financiacion = forms.CharField(
        label="Plan de financiación del déficit",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Obligatorio si el resultado es un déficit (regla V-006).",
    )
    endeudamiento = _dinero(
        "Endeudamiento nuevo previsto en el ejercicio (€)",
        help_text="Déjalo en 0,00 si no hay. Se contrasta con el límite legal (regla L-005).",
    )
