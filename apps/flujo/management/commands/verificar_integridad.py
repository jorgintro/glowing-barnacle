"""Recalcula la huella de cada versión sellada y revisa la cadena de transiciones."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.flujo.sello import verificar_integridad
from apps.presupuesto.models import VersionPresupuesto


class Command(BaseCommand):
    help = "Comprueba que ninguna versión sellada ha sido manipulada. Falla si encuentra algo."

    def handle(self, *args: Any, **opciones: Any) -> None:
        versiones = VersionPresupuesto.objects.select_related("ejercicio").order_by(
            "ejercicio__anio", "numero"
        )
        malas = 0
        for v in versiones:
            res = verificar_integridad(v)
            etiqueta = f"{v.ejercicio.anio} v{v.numero} ({v.get_estado_display()})"
            if res.ok:
                self.stdout.write(f"  correcta  {etiqueta}")
            else:
                malas += 1
                self.stdout.write(self.style.ERROR(f"  ALTERADA  {etiqueta}"))
                for problema in res.problemas:
                    self.stdout.write(f"            - {problema}")
        if malas:
            raise CommandError(f"{malas} versión(es) con problemas de integridad.")
        self.stdout.write(
            self.style.SUCCESS(f"Todas las versiones ({versiones.count()}) son íntegras.")
        )
