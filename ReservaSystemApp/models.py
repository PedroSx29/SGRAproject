from django.db import models

# Create your models here.

class Administrador(models.Model):
    idAdmin = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50)
    usuario = models.CharField(max_length=50)
    email = models.CharField(max_length=50)
    contraseña = models.CharField(max_length=30)

    def __str__(self):
        return f"{self.nombre} ({self.usuario})"
    
    class Meta:
        db_table = 'administrador'

class DisponibilidadParque(models.Model):
    id = models.AutoField(primary_key=True)
    fecha = models.DateField()
    horaInicio = models.TimeField()
    horaFin = models.TimeField()
    capacidadMaxima = models.IntegerField()
    capacidadActual = models.IntegerField()
    
    def __str__(self):
        return f"{self.fecha} de {self.horaInicio} a {self.horaFin}"
    
    class Meta:
        db_table = 'disponibilidadParque'
        unique_together = ['fecha', 'horaInicio']

class EncargadoAcceso(models.Model):
    idEncargado = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50)
    rut = models.CharField(max_length=11)
    usuario = models.CharField(max_length=50)
    contraseña = models.CharField(max_length=30)

    def __str__(self):
        return f"{self.nombre} - RUT: {self.rut}"
    
    class Meta:
        db_table = 'encargadoAcceso'

class DocumentoAcceso(models.Model):
    idDocumento = models.AutoField(primary_key=True)
    codigoQR = models.ImageField()
    fechaGeneracion = models.DateField()
    rutVisitante = models.BooleanField()

    def __str__(self):
        return f"Documento {self.idDocumento} - Fecha: {self.fechaGeneracion}"
    
    class Meta:
        db_table = 'documentoAcceso'
    
class Visitante(models.Model):
    rut = models.CharField(max_length=11, primary_key=True)
    nombre = models.CharField(max_length=30)
    apellido = models.CharField(max_length=30)
    telefono = models.CharField(max_length=15)
    correo = models.CharField(max_length=35)
    edad = models.IntegerField()

    def __str__(self):
        return f"{self.nombre} {self.apellido} - RUT: {self.rut}"
    
    class Meta:
        db_table = 'visitante'

class SistemaNotificaciones(models.Model):
    idNotificacion = models.AutoField(primary_key=True)
    fechaEnvio = models.DateField()
    tipo = models.CharField(max_length=40)
    mensaje = models.CharField(max_length=400)

    def __str__(self):
        return f"{self.tipo} - {self.fechaEnvio}"
    
    class Meta: 
        db_table = 'sistemaNotificaciones'

class TipoVisita(models.Model):
    nombre = models.CharField(max_length=55, unique=True)
    descripcion = models.CharField(max_length=200)

    def __str__(self):
        return self.nombre
    
    class Meta:
        db_table = 'tipoVisita'
    
class Acompañante(models.Model):
    rut = models.CharField(max_length=11, primary_key=True)
    rutVisitante = models.ForeignKey(Visitante, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=60)
    edad = models.IntegerField()

    def __str__(self):
        return f"{self.nombre} - RUT: {self.rut}"
    
    class Meta:
        db_table = 'acompañante'

class Reserva(models.Model):
    class Estado(models.TextChoices):
        ACTIVO = 'ACTIVO', 'Activo'
        UTILIZADO = 'UTILIZADO', 'Utilizado'
        VENCIDO = 'VENCIDO', 'Vencido'

    idReserva = models.AutoField(primary_key=True)
    visitante = models.ForeignKey(
        Visitante,
        on_delete=models.CASCADE,
        related_name='reservas'
    )
    disponibilidad = models.ForeignKey(
        DisponibilidadParque,
        on_delete=models.CASCADE,
        related_name='reservas',
        null=True,  # Permitir valores nulos temporalmente
        default=None  # Valor por defecto None
    )
    cantidadVisitantes = models.IntegerField()
    tipoVisita = models.ForeignKey(
        TipoVisita, 
        on_delete=models.CASCADE,
        related_name='reservas',
        null=True,
        to_field='nombre'
    )
    estadoReserva = models.CharField(max_length=30, choices=Estado.choices, default=Estado.ACTIVO)

    def __str__(self):
        return f"Reserva {self.idReserva} - {self.visitante.nombre}"

    class Meta:
        db_table = 'reserva'