from django.urls import path

from . import views

app_name = "anexos"

urlpatterns = [
    path("presupuestos/version/<int:pk>/memoria/", views.memoria, name="memoria"),
    path(
        "presupuestos/version/<int:pk>/memoria/<slug:clave>/",
        views.memoria_editar,
        name="memoria_editar",
    ),
    path("presupuestos/version/<int:pk>/tesoreria/", views.tesoreria, name="tesoreria"),
    path("anexos/", views.configuracion, name="configuracion"),
    path("anexos/secciones/nueva/", views.seccion_cfg_nueva, name="seccion_cfg_nueva"),
    path("anexos/secciones/<int:pk>/", views.seccion_cfg_editar, name="seccion_cfg"),
    path(
        "anexos/secciones/<int:pk>/restablecer/",
        views.seccion_cfg_restablecer,
        name="seccion_cfg_restablecer",
    ),
]
