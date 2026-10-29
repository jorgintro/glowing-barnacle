from django import forms
from django.contrib.auth import password_validation

from .models import Usuario
from .roles import Rol


class CrearUsuarioForm(forms.Form):
    username = forms.CharField(label="Nombre de usuario", max_length=150)
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    email = forms.EmailField(label="Correo electrónico", required=False)
    password = forms.CharField(
        label="Contraseña inicial", widget=forms.PasswordInput, help_text="Mínimo 12 caracteres."
    )
    roles = forms.MultipleChoiceField(
        label="Roles", choices=Rol.choices, widget=forms.CheckboxSelectMultiple
    )

    def clean_username(self) -> str:
        nombre = self.cleaned_data["username"]
        if Usuario.objects.filter(username__iexact=nombre).exists():
            raise forms.ValidationError("Ya existe un usuario con ese nombre.")
        return nombre

    def clean_password(self) -> str:
        clave = self.cleaned_data["password"]
        password_validation.validate_password(clave)
        return clave


class EditarRolesForm(forms.Form):
    roles = forms.MultipleChoiceField(
        label="Roles", choices=Rol.choices, widget=forms.CheckboxSelectMultiple, required=False
    )
    motivo = forms.CharField(
        label="Motivo (obligatorio si se retira un rol)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class BajaForm(forms.Form):
    motivo = forms.CharField(label="Motivo de la baja", widget=forms.Textarea(attrs={"rows": 2}))
