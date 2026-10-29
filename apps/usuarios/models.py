from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .roles import Rol


class Usuario(AbstractUser):
    """Identidad nominal. Los usuarios no se borran: se dan de baja con fecha (§10)."""

    fecha_baja = models.DateTimeField(null=True, blank=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def nombre_visible(self) -> str:
        return self.get_full_name() or self.get_username()

    def roles_vigentes(self) -> list[str]:
        """Roles asignados y no anulados, en el orden de ``Rol``."""
        vigentes = set(
            self.asignaciones.filter(fecha_fin__isnull=True).values_list("rol", flat=True)
        )
        return [r.value for r in Rol if r.value in vigentes]


class AsignacionRol(models.Model):
    """Un usuario puede tener varios roles, pero actúa con uno solo por sesión."""

    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="asignaciones")
    rol = models.CharField(max_length=30, choices=Rol.choices)
    fecha_inicio = models.DateTimeField(default=timezone.now)
    fecha_fin = models.DateTimeField(null=True, blank=True)
    asignado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    motivo_fin = models.TextField(blank=True)

    class Meta:
        verbose_name = "asignación de rol"
        verbose_name_plural = "asignaciones de rol"
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "rol"],
                condition=Q(fecha_fin__isnull=True),
                name="un_rol_vigente_por_usuario",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.usuario} · {self.get_rol_display()}"
