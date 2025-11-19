from django.contrib import admin
from ReservaSystemApp.models import DisponibilidadParque, Reserva, Acompañante, EncargadoAcceso, Administrador, DocumentoAcceso, SistemaNotificaciones, TipoVisita, Visitante

# Register your models here.
admin.site.register(DisponibilidadParque)
admin.site.register(Acompañante)
admin.site.register(Reserva)
admin.site.register(EncargadoAcceso)
admin.site.register(Administrador)
admin.site.register(DocumentoAcceso)
admin.site.register(SistemaNotificaciones)
admin.site.register(TipoVisita)
admin.site.register(Visitante)