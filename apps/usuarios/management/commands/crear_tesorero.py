"""Crea el primer Tesorero (arranque del sistema). No sirve para crear más usuarios."""

import os
from typing import Any

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.auditoria.servicios import Contexto, registrar
from apps.usuarios.models import AsignacionRol, Usuario
from apps.usuarios.roles import Rol


class Command(BaseCommand):
    help = "Crea el primer usuario con rol Tesorero. Contraseña desde TESORERO_CLAVE o por prompt."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--usuario", default=os.environ.get("TESORERO_USUARIO", ""))
        parser.add_argument("--nombre", default="")
        parser.add_argument("--apellidos", default="")

    @transaction.atomic
    def handle(self, *args: Any, **opciones: Any) -> None:
        if AsignacionRol.objects.filter(rol=Rol.TESORERO, fecha_fin__isnull=True).exists():
            self.stdout.write("Ya existe un Tesorero; no se hace nada.")
            return
        nombre_usuario = opciones["usuario"] or input("Nombre de usuario: ").strip()
        clave = os.environ.get("TESORERO_CLAVE", "")
        if not clave:
            from getpass import getpass

            clave = getpass("Contraseña (mínimo 12 caracteres): ")
        try:
            password_validation.validate_password(clave)
        except ValidationError as error:
            raise CommandError("; ".join(error.messages)) from error
        usuario = Usuario(
            username=nombre_usuario,
            first_name=opciones["nombre"],
            last_name=opciones["apellidos"],
        )
        usuario.set_password(clave)
        usuario.save()
        AsignacionRol.objects.create(usuario=usuario, rol=Rol.TESORERO)
        registrar(
            Contexto(usuario, Rol.TESORERO),
            accion="usuario.crear",
            entidad="Usuario",
            entidad_id=usuario.pk,
            despues={"username": nombre_usuario, "roles": [Rol.TESORERO]},
            motivo="Alta inicial del sistema",
        )
        self.stdout.write(self.style.SUCCESS(f"Tesorero «{nombre_usuario}» creado."))
