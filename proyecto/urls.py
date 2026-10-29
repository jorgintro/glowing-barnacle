from django.urls import include, path

from apps.usuarios import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("", include("apps.usuarios.urls")),
]
