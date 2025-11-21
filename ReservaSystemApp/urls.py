from django.urls import path
from . import views

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('form/', views.form, name='form'),
    path('disponibilidad/', views.mostrarDisponibilidad, name='mostrar_disponibilidad'),
    path('guardar-reserva/', views.guardarReserva, name='guardar_reserva'),
    path('tipos-visita/', views.mostrarTipoVisita, name='mostrar_tipo_visita'),
    path('valreserva', views.validarReserva, name='valreserva'),
    path('validar-reserva/', views.validarReserva, name='validar_reserva'),

    path('reserva/modificar/<int:reserva_id>/', views.modificarReserva, name='modificar_reserva'),
    path('reserva/guardar-modificacion/<int:reserva_id>/', views.guardarModificacionReserva, name='guardar_modificacion_reserva'),

    path('monitoreo/dashboard/', views.dashboardMonitoreo, name='dashboard_monitoreo'),
]