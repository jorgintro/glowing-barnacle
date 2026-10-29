from django.urls import path

from . import views

app_name = "presupuesto"

urlpatterns = [
    path("presupuestos/", views.lista, name="lista"),
    path("presupuestos/ejercicio/nuevo/", views.ejercicio_nuevo, name="ejercicio_nuevo"),
    path("presupuestos/version/<int:pk>/", views.version, name="version"),
    path(
        "presupuestos/version/<int:pk>/lineas/nueva/",
        views.linea_elegir_partida,
        name="linea_elegir",
    ),
    path(
        "presupuestos/version/<int:pk>/lineas/nueva/<str:partida>/",
        views.linea_nueva,
        name="linea_nueva",
    ),
    path(
        "presupuestos/version/<int:pk>/lineas/<int:linea_pk>/",
        views.linea_editar,
        name="linea_editar",
    ),
    path(
        "presupuestos/version/<int:pk>/lineas/<int:linea_pk>/anular/",
        views.linea_anular,
        name="linea_anular",
    ),
    path("configuracion/", views.configuracion, name="configuracion"),
]
