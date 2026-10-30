"""Datos de la organización: denominaciones, cargos y personas (panel de administración).

Son datos reales de la organización y los introduce el Tesorero. No se precarga ninguno.
Las personas llevan DNI (dato personal): ver ``docs/proteccion_datos.md``.
"""

from typing import Any

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Organizacion(models.Model):
    """Registro único con los datos que aparecen en los certificados."""

    nombre = models.CharField(max_length=200, default="Iniciativa Complutense")
    localidad = models.CharField(max_length=120, default="Alcalá de Henares")
    denominacion_tesoreria = models.CharField(
        "cómo se llama el cargo de Tesorería",
        max_length=60,
        default="Tesorero",
        help_text="Por ejemplo «Tesorero», «Tesorera» o «Gerente». Sale en los certificados.",
    )

    class Meta:
        verbose_name = "organización"
        verbose_name_plural = "organización"

    def __str__(self) -> str:
        return self.nombre

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.pk = 1  # registro único
        super().save(*args, **kwargs)

    @classmethod
    def obtener(cls) -> "Organizacion":
        return cls.objects.get_or_create(pk=1)[0]


class Cargo(models.Model):
    """Cargo, ocupación o denominación (Tesorero/a, Gerente, Secretario/a, Vocal…)."""

    denominacion = models.CharField(max_length=120)
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)
    creado = models.DateTimeField(default=timezone.now)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["orden", "denominacion"]
        verbose_name = "cargo"
        verbose_name_plural = "cargos"
        constraints = [
            models.UniqueConstraint(Lower("denominacion"), name="un_cargo_por_denominacion"),
        ]

    def __str__(self) -> str:
        return self.denominacion


class Persona(models.Model):
    """Miembro de la organización con sus cargos. Nunca se borra: se da de baja con motivo."""

    nombre = models.CharField(max_length=120)
    apellidos = models.CharField(max_length=200)
    dni = models.CharField("DNI/NIE", max_length=15)
    cargos = models.ManyToManyField(Cargo, blank=True, related_name="personas")
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="persona",
        help_text="Cuenta con la que esta persona entra en el sistema (si tiene).",
    )
    activa = models.BooleanField(default=True)
    fecha_alta = models.DateTimeField(default=timezone.now)
    fecha_baja = models.DateTimeField(null=True, blank=True)
    motivo_baja = models.TextField(blank=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["apellidos", "nombre"]
        verbose_name = "persona"
        verbose_name_plural = "personas"
        constraints = [
            models.UniqueConstraint(fields=["dni", "es_demo"], name="una_persona_por_dni"),
        ]

    def __str__(self) -> str:
        return self.nombre_completo

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellidos}".strip()

    def cargos_texto(self) -> str:
        return " y ".join(self.cargos.filter(activo=True).values_list("denominacion", flat=True))
