import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistroAuditoria",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("usuario_texto", models.CharField(blank=True, help_text="Nombre tal como se tecleó.", max_length=150, verbose_name="usuario (texto)")),
                ("rol_activo", models.CharField(blank=True, max_length=30)),
                ("accion", models.CharField(db_index=True, max_length=50)),
                ("entidad", models.CharField(db_index=True, max_length=60)),
                ("entidad_id", models.CharField(blank=True, max_length=64)),
                ("antes", models.JSONField(blank=True, null=True)),
                ("despues", models.JSONField(blank=True, null=True)),
                ("motivo", models.TextField(blank=True)),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                ("es_demo", models.BooleanField(default=False)),
                ("usuario", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "registro de auditoría",
                "verbose_name_plural": "registros de auditoría",
                "ordering": ["-fecha", "-id"],
            },
        ),
    ]
