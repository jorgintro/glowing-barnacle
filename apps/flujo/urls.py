from django.urls import path

from . import views

app_name = "flujo"

urlpatterns = [
    path("presupuestos/version/<int:pk>/proponer/", views.proponer, name="proponer"),
    path("presupuestos/version/<int:pk>/devolver/", views.devolver, name="devolver"),
    path("presupuestos/version/<int:pk>/votacion/", views.votacion, name="votacion"),
    path("presupuestos/version/<int:pk>/votacion/votar/", views.votar, name="votar"),
    path("presupuestos/version/<int:pk>/votacion/cerrar/", views.cerrar_votacion, name="cerrar"),
    path("presupuestos/version/<int:pk>/convocatoria/", views.convocatoria, name="convocatoria"),
    path("presupuestos/version/<int:pk>/ratificar/", views.ratificar, name="ratificar"),
    path("presupuestos/version/<int:pk>/modificar/", views.modificar, name="modificar"),
    path("presupuestos/version/<int:pk>/historial/", views.historial, name="historial"),
    path("presupuestos/version/<int:pk>/comentarios/", views.comentarios, name="comentarios"),
    path(
        "presupuestos/version/<int:pk>/comentarios/<int:comentario_pk>/resolver/",
        views.resolver_comentario,
        name="resolver_comentario",
    ),
    path("presupuestos/ejercicio/<int:pk>/prorroga/", views.prorroga, name="prorroga"),
    path("auditoria/", views.auditoria, name="auditoria"),
]
