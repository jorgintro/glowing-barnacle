"""Carga los datos de demostración (ficticios). Se borran con ``borrar_demo``."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.auditoria.servicios import Contexto
from apps.presupuesto import demo
from apps.presupuesto.sincronizacion import sincronizar_todo


class Command(BaseCommand):
    help = "Carga ejercicios, versiones y usuarios FICTICIOS de demostración."

    def handle(self, *args: Any, **opciones: Any) -> None:
        if not settings.PERMITIR_DATOS_DEMO:
            raise CommandError(
                "La carga de datos de demostración está desactivada (PERMITIR_DATOS_DEMO=0)."
            )
        if demo.existe_demo():
            raise CommandError("Ya hay datos de demostración. Bórralos antes con borrar_demo.")
        sincronizar_todo()
        credenciales = demo.cargar_demo(Contexto(None, "", None))
        self.stdout.write(self.style.WARNING(demo.AVISO))
        self.stdout.write(
            "Usuarios de demostración (anota las contraseñas: no se vuelven a mostrar):"
        )
        for usuario, clave in credenciales.items():
            self.stdout.write(f"  {usuario}  {clave}")
        self.stdout.write(self.style.SUCCESS("Datos de demostración cargados."))
