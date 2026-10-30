from typing import Any

from django import forms

from apps.presupuesto.forms import ImporteField

from .configuracion import CAMPOS_CONFIANZA, CAMPOS_TIPO
from .models import ProcesoElectoral, SeccionMemoriaCfg


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
            "ambito",
            "longitud_minima",
            "ayuda",
            "plantilla",
        ]
        labels = {
            "titulo": "Título",
            "orden": "Orden (1 sale la primera)",
            "obligatoria": "Obligatoria: sin ella no se puede proponer",
            "activa": "Activa (si la desmarcas, deja de pedirse)",
            "ambito": "En qué presupuesto se pide",
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

    porcentaje_aviso_limite_campana = ImporteField(
        label="Campaña: avisar al llegar a este % del límite de gasto electoral",
        required=False,
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "class": "importe"}),
        help_text="Vacío = no se vigila la cercanía al límite.",
    )
    semaforo_ambar_pct = ImporteField(
        label="Comparativa: desviación (%) a partir de la cual el semáforo pasa a ámbar",
        required=False,
        max_digits=6,
        decimal_places=2,
        min_value=0,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "class": "importe"}),
    )
    semaforo_rojo_pct = ImporteField(
        label="Comparativa: desviación (%) a partir de la cual el semáforo pasa a rojo",
        required=False,
        max_digits=6,
        decimal_places=2,
        min_value=0,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "class": "importe"}),
        help_text="Sin ámbar y rojo, el semáforo no se calcula.",
    )
    semaforo_importe_minimo = ImporteField(
        label="Comparativa: desviación mínima en euros para que cuente",
        required=False,
        max_digits=14,
        decimal_places=2,
        min_value=0,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "class": "importe"}),
        help_text="Las desviaciones menores de este importe salen en verde.",
    )

    def clean(self) -> dict[str, Any]:
        datos = super().clean() or {}
        ambar, rojo = datos.get("semaforo_ambar_pct"), datos.get("semaforo_rojo_pct")
        if ambar is not None and rojo is not None and rojo < ambar:
            raise forms.ValidationError("El rojo no puede ser menor que el ámbar.")
        if (ambar is None) != (rojo is None):
            raise forms.ValidationError("Indica a la vez el ámbar y el rojo, o ninguno.")
        return datos

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


class ProcesoElectoralForm(forms.ModelForm):
    class Meta:
        model = ProcesoElectoral
        fields = [
            "denominacion",
            "fecha_convocatoria",
            "fecha_elecciones",
            "fecha_proclamacion",
            "habitantes_derecho",
            "provincias_adicional",
            "subvencion_envio_aplicable",
            "electores_envio",
            "concejales_previstos",
            "votos_previstos",
            "observaciones",
        ]
        widgets = {
            "fecha_convocatoria": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fecha_elecciones": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fecha_proclamacion": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }
        help_texts = {
            "habitantes_derecho": "Población de derecho de las circunscripciones donde se "
            "presentan candidaturas. Con ella se calcula el límite de gasto.",
            "provincias_adicional": "Provincias en las que se concurre, al menos, al 50 % de sus "
            "municipios (dan derecho a un gasto adicional). Normalmente 0.",
            "subvencion_envio_aplicable": "Márcalo solo si se cumplen los requisitos legales del "
            "envío directo: su subvención queda fuera del límite.",
            "electores_envio": "Electores a los que se enviará propaganda de forma directa.",
            "concejales_previstos": "Solo para estimar la subvención; es una previsión tuya.",
            "votos_previstos": "Solo para estimar la subvención; es una previsión tuya.",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for campo in ("fecha_convocatoria", "fecha_elecciones", "fecha_proclamacion"):
            fecha = self.fields[campo]
            assert isinstance(fecha, forms.DateField)
            fecha.input_formats = ["%Y-%m-%d", "%d/%m/%Y"]
        self.fields["provincias_adicional"].required = False


class ImportarEjecucionForm(forms.Form):
    fichero = forms.FileField(
        label="Fichero CSV de ejecución real",
        help_text="Tres columnas separadas por «;»: codigo;mes;importe (importe con coma decimal).",
    )
    mes_corte = forms.TypedChoiceField(
        label="Mes de corte (último mes con datos)",
        choices=[(m, f"{m:02d}") for m in range(1, 13)],
        coerce=int,
    )


class MotivoAnulacionForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo de la anulación", widget=forms.Textarea(attrs={"rows": 3})
    )
