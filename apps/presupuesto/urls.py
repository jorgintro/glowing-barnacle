from django.urls import path

from . import views

app_name = "presupuesto"

urlpatterns = [
    path("presupuestos/", views.lista, name="lista"),
    path("presupuestos/ejercicio/nuevo/", views.ejercicio_nuevo, name="ejercicio_nuevo"),
    path(
        "presupuestos/ejercicio/<int:pk>/electoral/",
        views.crear_electoral,
        name="crear_electoral",
    ),
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
    path("presupuestos/version/<int:pk>/validaciones/", views.validaciones, name="validaciones"),
    path("presupuestos/version/<int:pk>/resultado/", views.resultado, name="resultado"),
    path(
        "presupuestos/version/<int:pk>/lineas/<int:linea_pk>/donantes/",
        views.linea_donaciones,
        name="linea_donaciones",
    ),
    path(
        "presupuestos/version/<int:pk>/donaciones/<int:donacion_pk>/anular/",
        views.donacion_anular,
        name="donacion_anular",
    ),
    path("donantes/", views.donantes_lista, name="donantes"),
    path("donantes/<int:pk>/baja/", views.donante_baja, name="donante_baja"),
    path("configuracion/", views.configuracion, name="configuracion"),
]
