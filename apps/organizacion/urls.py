from django.urls import path

from . import views

app_name = "organizacion"

urlpatterns = [
    path("organizacion/", views.panel, name="panel"),
    path("organizacion/datos/", views.guardar_datos, name="guardar_datos"),
    path("organizacion/cargos/", views.guardar_cargos, name="guardar_cargos"),
    path("organizacion/personas/nueva/", views.persona_nueva, name="persona_nueva"),
    path("organizacion/personas/<int:pk>/", views.persona_editar, name="persona_editar"),
    path("organizacion/personas/<int:pk>/baja/", views.persona_baja, name="persona_baja"),
]
