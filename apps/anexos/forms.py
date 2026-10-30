from typing import Any

from django import forms

from apps.presupuesto.forms import ImporteField

from .configuracion import CAMPOS_CONFIANZA, CAMPOS_TIPO
from .models import SeccionMemoriaCfg


def _porcentaje(etiqueta: str, **kw: Any) -> ImporteField:
    return ImporteField(
        label=etiqueta,
        required=False,
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "class": "importe"}),
        **kw,
    )


class TextoSeccionForm(forms.Form):
    texto = forms.CharField(label="Texto de la sección", widget=forms.Textarea(attrs={"rows": 16}))


class SaldoInicialForm(forms.Form):
    saldo = ImporteField(
        label="Saldo inicial de tesorería (caja y bancos a 1 de enero)",
        required=False,
        max_digits=14,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "class": "importe"}),
    )


class SeccionCfgForm(forms.ModelForm):
    class Meta:
        model = SeccionMemoriaCfg
        fields = [
            "titulo",
            "orden",
            "obligatoria",
            "activa",
            "solo_con_proceso_electoral",
            "longitud_minima",
            "ayuda",
            "plantilla",
        ]
        labels = {
            "titulo": "Título",
            "orden": "Orden (1 sale la primera)",
            "obligatoria": "Obligatoria: sin ella no se puede proponer",
            "activa": "Activa (si la desmarcas, deja de pedirse)",
            "solo_con_proceso_electoral": "Solo si el ejercicio tiene proceso electoral",
            "longitud_minima": "Caracteres mínimos (vacío = sin mínimo)",
            "ayuda": "Texto de ayuda que ve quien redacta",
            "plantilla": "Plantilla (texto con el que arranca la sección)",
        }
        widgets = {
            "ayuda": forms.Textarea(attrs={"rows": 4}),
            "plantilla": forms.Textarea(attrs={"rows": 10}),
        }


class NuevaSeccionForm(forms.Form):
    titulo = forms.CharField(label="Título de la sección nueva", max_length=150)


class ParametrosForm(forms.Form):
    variaciones_destacadas = forms.IntegerField(
        label="Variaciones que destaca el resumen ejecutivo",
        min_value=0,
        max_value=50,
        help_text="Las mayores diferencias con el ejercicio anterior que salen en el resumen.",
    )
    marcas_pendiente = forms.CharField(
        label="Marcas de «pendiente» (una por línea)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Si alguna aparece en una sección, la memoria se considera sin terminar.",
    )
    saldo_minimo_tesoreria = ImporteField(
        label="Saldo mínimo de tesorería",
        required=False,
        max_digits=14,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "class": "importe"}),
        help_text="Por debajo se avisa de tensión de tesorería. Vacío = no se comprueba.",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for confianza, campo in CAMPOS_CONFIANZA.items():
            self.fields[campo] = _porcentaje(
                f"Prudente · descuento a ingresos de confianza {confianza.label.lower()} (%)"
            )
        for tipo, campo in CAMPOS_TIPO.items():
            self.fields[campo] = _porcentaje(
                f"Escenario ajustado · descuento a los gastos {tipo.label.lower()}s (%)"
            )
