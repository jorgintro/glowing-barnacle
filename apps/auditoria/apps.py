from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    name = "apps.auditoria"
    label = "auditoria"
    verbose_name = "Auditoría"

    def ready(self) -> None:
        from . import senales  # noqa: F401
