from typing import Any

from django import forms

from apps.presupuesto.models import Linea, VersionPresupuesto

from .models import ResultadoRatificacion, Voto

FECHA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def _fecha(etiqueta: str, **kw: Any) -> forms.DateField:
    return forms.DateField(
        label=etiqueta,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        **kw,
    )


class ProponerForm(forms.Form):
    avisos = forms.MultipleChoiceField(
        label="Avisos que acepto (queda constancia)",
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    confirmar = forms.BooleanField(
        label="Confirmo que quiero proponer esta versión a la Comisión Permanente. "
        "Quedará sellada y no se podrá modificar."
    )

    def __init__(self, *args: Any, avisos: list[tuple[str, str]], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        campo = self.fields["avisos"]
        assert isinstance(campo, forms.MultipleChoiceField)
        campo.choices = avisos


class MotivoForm(forms.Form):
    motivo = forms.CharField(label="Motivo", widget=forms.Textarea(attrs={"rows": 3}))


class VotarForm(forms.Form):
    voto = forms.ChoiceField(label="Tu voto", choices=Voto.choices, widget=forms.RadioSelect)


class CerrarVotacionForm(forms.Form):
    observaciones = forms.CharField(
        label="Observaciones (opcional)", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    confirmar = forms.BooleanField(
        label="Confirmo que quiero cerrar la votación. Los votos quedarán inalterables."
    )


class ConvocatoriaForm(forms.Form):
    fecha_convocatoria = _fecha("Fecha en que se convocó la Junta")
    fecha_sesion = _fecha("Fecha de la sesión de la Junta")
    referencia = forms.CharField(label="Referencia (opcional)", max_length=200, required=False)


class RatificarForm(forms.Form):
    fecha_sesion = _fecha("Fecha de la sesión de la Junta")
    resultado = forms.ChoiceField(
        label="Resultado", choices=ResultadoRatificacion.choices, widget=forms.RadioSelect
    )
    referencia_acta = forms.CharField(label="Referencia al acta", max_length=300)
    observaciones = forms.CharField(
        label="Observaciones (opcional)", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    acepto_aviso = forms.BooleanField(
        label="Acepto el aviso de la convocatoria y dejo constancia", required=False
    )


class _LineaField(forms.ModelChoiceField):
    def label_from_instance(self, obj: Any) -> str:
        return f"{obj.codigo} · {obj.denominacion}"


class ComentarioForm(forms.Form):
    texto = forms.CharField(label="Comentario", widget=forms.Textarea(attrs={"rows": 3}))
    linea = _LineaField(
        label="Línea a la que se refiere (opcional)", queryset=Linea.objects.none(), required=False
    )

    def __init__(self, *args: Any, version: VersionPresupuesto, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        campo = self.fields["linea"]
        assert isinstance(campo, forms.ModelChoiceField)
        campo.queryset = Linea.objects.filter(version=version, anulada=False).order_by("codigo")


class FiltroAuditoriaForm(forms.Form):
    usuario = forms.CharField(label="Usuario", required=False)
    accion = forms.CharField(label="Acción (contiene)", required=False)
    entidad = forms.CharField(label="Entidad (contiene)", required=False)
    desde = _fecha("Desde", required=False)
    hasta = _fecha("Hasta", required=False)
