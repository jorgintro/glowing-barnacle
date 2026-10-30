from django.urls import path

from . import views

app_name = "salidas"

urlpatterns = [
    path("presupuestos/version/<int:pk>/certificados/", views.certificados, name="certificados"),
    path("presupuestos/version/<int:pk>/certificado/", views.certificado, name="certificado"),
]
