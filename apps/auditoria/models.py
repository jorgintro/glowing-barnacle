"""Registro de auditoría inmutable (§13.1).

La inmutabilidad se garantiza en tres niveles: este modelo (no permite modificar ni borrar),
el gestor (bloquea ``update``/``delete`` masivos) y, sobre todo, disparadores en PostgreSQL
creados en la migración 0002, que rechazan cualquier ``UPDATE``, ``DELETE`` o ``TRUNCATE``.
La única excepción son las filas marcadas ``es_demo`` y solo mientras el comando de borrado de
datos de demostración activa ``presupuesto.modo_demo``.
"""

from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditoriaInalterable(Exception):
    """Se intentó modificar o borrar un registro de auditoría."""


class _ConsultaInalterable(models.QuerySet["RegistroAuditoria"]):
    def update(self, **kwargs: Any) -> int:
        raise AuditoriaInalterable("El registro de auditoría no se puede modificar.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise AuditoriaInalterable("El registro de auditoría no se puede borrar.")


class RegistroAuditoria(models.Model):
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    usuario_texto = models.CharField(
        "usuario (texto)", max_length=150, blank=True, help_text="Nombre tal como se tecleó."
    )
    rol_activo = models.CharField(max_length=30, blank=True)
    accion = models.CharField(max_length=50, db_index=True)
    entidad = models.CharField(max_length=60, db_index=True)
    entidad_id = models.CharField(max_length=64, blank=True)
    antes = models.JSONField(null=True, blank=True)
    despues = models.JSONField(null=True, blank=True)
    motivo = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    es_demo = models.BooleanField(default=False)

    objects = _ConsultaInalterable.as_manager()

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"
        ordering = ["-fecha", "-id"]

    def __str__(self) -> str:
        return f"{self.fecha:%d/%m/%Y %H:%M:%S} · {self.accion} · {self.entidad}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AuditoriaInalterable("El registro de auditoría no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise AuditoriaInalterable("El registro de auditoría no se puede borrar.")
