"""Carga la configuración (cuadro, parámetros legales y valores propuestos de los anexos)."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.anexos.configuracion import asegurar_configuracion
from apps.presupuesto.configuracion import ErrorConfiguracion
from apps.presupuesto.sincronizacion import sincronizar_todo


class Command(BaseCommand):
    help = "Sincroniza la configuración (cuadro de cuentas y parámetros legales). Es idempotente."

    def handle(self, *args: Any, **opciones: Any) -> None:
        try:
            resultados = sincronizar_todo()
            asegurar_configuracion(False)  # memoria y tesorería: solo siembra lo que falte
        except ErrorConfiguracion as error:
            raise CommandError(str(error)) from error
        for nombre, r in resultados.items():
            self.stdout.write(
                f"{nombre}: {r.creados} creados, {r.actualizados} actualizados, "
                f"{r.desactivados} desactivados"
            )
