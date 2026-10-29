"""Carga config/cuadro_cuentas.yaml y config/parametros_legales.yaml en la base de datos."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.presupuesto.configuracion import ErrorConfiguracion
from apps.presupuesto.sincronizacion import sincronizar_todo


class Command(BaseCommand):
    help = "Sincroniza la configuración (cuadro de cuentas y parámetros legales). Es idempotente."

    def handle(self, *args: Any, **opciones: Any) -> None:
        try:
            resultados = sincronizar_todo()
        except ErrorConfiguracion as error:
            raise CommandError(str(error)) from error
        for nombre, r in resultados.items():
            self.stdout.write(
                f"{nombre}: {r.creados} creados, {r.actualizados} actualizados, "
                f"{r.desactivados} desactivados"
            )
