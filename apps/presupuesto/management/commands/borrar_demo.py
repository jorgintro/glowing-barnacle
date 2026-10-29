"""Borra los datos de demostración y SOLO esos. Los datos reales no se tocan."""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.auditoria.servicios import Contexto
from apps.presupuesto import demo


class Command(BaseCommand):
    help = "Borra todos los datos de demostración (ficticios)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--confirmar", action="store_true", help="Confirma el borrado.")

    def handle(self, *args: Any, **opciones: Any) -> None:
        if not demo.existe_demo():
            self.stdout.write("No hay datos de demostración que borrar.")
            return
        if not opciones["confirmar"]:
            self.stdout.write(
                "Esto borra todos los datos de demostración (y solo esos). "
                "Repite el comando con --confirmar."
            )
            return
        resumen = demo.borrar_demo(Contexto(None, "", None))
        for nombre, n in resumen.items():
            self.stdout.write(f"  {nombre}: {n}")
        self.stdout.write(self.style.SUCCESS("Datos de demostración borrados."))
