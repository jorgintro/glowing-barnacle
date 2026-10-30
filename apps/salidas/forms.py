from typing import Any

from django import forms

from apps.organizacion.models import Persona

from .certificados import TIPOS


class _PersonaField(forms.ModelChoiceField):
    def label_from_instance(self, obj: Any) -> str:
        return f"{obj.nombre_completo} · {obj.cargos_texto()}"


class CertificadoForm(forms.Form):
    tipo = forms.ChoiceField(label="Qué se certifica", choices=list(TIPOS.items()))
    firmante = _PersonaField(label="Quién certifica", queryset=Persona.objects.none())
    visto_bueno = _PersonaField(
        label="Visto bueno de (opcional)", queryset=Persona.objects.none(), required=False
    )
    incluir_votos = forms.BooleanField(
        label="Incluir el voto de cada miembro (por defecto solo salen los totales)",
        required=False,
    )

    def __init__(self, *args: Any, tipos: list[str], es_demo: bool, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        tipo = self.fields["tipo"]
        assert isinstance(tipo, forms.ChoiceField)
        tipo.choices = [(k, v) for k, v in TIPOS.items() if k in tipos]
        personas = (
            Persona.objects.filter(activa=True, es_demo=es_demo, cargos__activo=True)
            .distinct()
            .order_by("apellidos", "nombre")
        )
        for nombre in ("firmante", "visto_bueno"):
            campo = self.fields[nombre]
            assert isinstance(campo, forms.ModelChoiceField)
            campo.queryset = personas
