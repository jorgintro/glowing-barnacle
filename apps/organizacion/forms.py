from typing import Any

from django import forms
from django.db.models import Q

from apps.usuarios.models import Usuario

from .models import Cargo, Persona


class OrganizacionForm(forms.Form):
    nombre = forms.CharField(label="Nombre de la organización", max_length=200)
    localidad = forms.CharField(label="Localidad (aparece en los certificados)", max_length=120)
    denominacion_tesoreria = forms.CharField(
        label="Cómo se llama el cargo de Tesorería",
        max_length=60,
        help_text="Por ejemplo «Tesorero», «Tesorera» o «Gerente».",
    )


class CargosForm(forms.Form):
    cargos = forms.CharField(
        label="Cargos, ocupaciones y denominaciones (uno por línea)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text="Escribe cada cargo en una línea. Los que quites se desactivan, no se borran.",
    )


class PersonaForm(forms.Form):
    nombre = forms.CharField(label="Nombre", max_length=120)
    apellidos = forms.CharField(label="Apellidos", max_length=200)
    dni = forms.CharField(label="DNI / NIE", max_length=15)
    cargos = forms.ModelMultipleChoiceField(
        label="Cargo o cargos",
        queryset=Cargo.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    usuario = forms.ModelChoiceField(
        label="Cuenta de usuario (opcional)", queryset=Usuario.objects.none(), required=False
    )

    def __init__(self, *args: Any, persona: Persona | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        campo_cargos = self.fields["cargos"]
        assert isinstance(campo_cargos, forms.ModelMultipleChoiceField)
        campo_cargos.queryset = Cargo.objects.filter(activo=True)
        libres = Q(persona__isnull=True)
        if persona is not None:
            libres |= Q(persona=persona)
        campo_usuario = self.fields["usuario"]
        assert isinstance(campo_usuario, forms.ModelChoiceField)
        campo_usuario.queryset = Usuario.objects.filter(is_active=True, es_demo=False).filter(
            libres
        )

    @classmethod
    def inicial_desde(cls, persona: Persona) -> dict[str, Any]:
        return {
            "nombre": persona.nombre,
            "apellidos": persona.apellidos,
            "dni": persona.dni,
            "cargos": list(persona.cargos.values_list("pk", flat=True)),
            "usuario": persona.usuario_id,
        }


class BajaPersonaForm(forms.Form):
    motivo = forms.CharField(label="Motivo de la baja", widget=forms.Textarea(attrs={"rows": 2}))
