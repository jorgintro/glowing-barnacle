from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("entrar/", views.EntrarView.as_view(), name="entrar"),
    path("salir/", views.salir, name="salir"),
    path("rol/", views.seleccionar_rol, name="seleccionar_rol"),
    path("usuarios/", views.lista, name="lista"),
    path("usuarios/nuevo/", views.crear, name="crear"),
    path("usuarios/<int:pk>/roles/", views.editar, name="editar"),
    path("usuarios/<int:pk>/baja/", views.baja, name="baja"),
]
