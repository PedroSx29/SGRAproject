from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db import connection
from django.utils import timezone
from ReservaSystemApp.models import (
    DisponibilidadParque, Visitante, Acompañante, Reserva, TipoVisita,
    RegistroCambioReserva, SistemaNotificaciones
)

# Helper function para el sistema de notificación (basado en models.py)
def crear_notificacion(tipo, mensaje):
    """Crea un registro de notificación."""
    SistemaNotificaciones.objects.create(
        fechaEnvio=timezone.now().date(),
        tipo=tipo,
        mensaje=mensaje
    )

# Create your views here.
def mostrarTipoVisita(request):
    tipos_visita = TipoVisita.objects.all().order_by('nombre')
    context = {
        'tipos_visita': tipos_visita
    }
    return render(request, 'form.html', context)

def inicio(request):
    return render(request, 'index.html')

def form(request):
    # Redirigir a mostrarDisponibilidad para que muestre los datos
    return mostrarDisponibilidad(request)

def mostrarDisponibilidad(request):
    try:
        # Obtener todas las disponibilidades y ordenarlas
        disponibilidades = DisponibilidadParque.objects.all().order_by('fecha', 'horaInicio')
        
        # Obtener tipos de visita
        tipos_visita = TipoVisita.objects.all().order_by('nombre')
        
        # Verificar si hay datos
        if not disponibilidades.exists():
            return render(request, 'form.html', {
                'error': 'No hay horarios disponibles',
                'tipos_visita': tipos_visita
            })
        
        context = {
            'form': disponibilidades,
            'tipos_visita': tipos_visita,
            'hay_datos': True
        }
        return render(request, 'form.html', context)
    except Exception as e:
        print(f"Error al obtener disponibilidades: {e}")
        return render(request, 'form.html', {'error': 'Error al cargar los horarios'})

@transaction.atomic
def guardarReserva(request):
    if request.method == 'POST':
        try:
            # ... (código existente para guardar reserva) ...
            # Esto debería ser el código original que ya tenías
            # ...
            # Obtener datos del visitante principal
            visitante_data = {
                'rut': request.POST.get('rut'),
                'nombre': request.POST.get('nombre'),
                'telefono': request.POST.get('telefono'),
                'correo': request.POST.get('correo'),
                'edad': int(request.POST.get('edad')),
                'apellido': '' # Deberías asegurarte de obtener el apellido si lo solicitas en el formulario
            }

            # Crear o actualizar visitante
            visitante, created = Visitante.objects.update_or_create(
                rut=visitante_data['rut'],
                defaults={
                    'nombre': visitante_data['nombre'],
                    'apellido': visitante_data['apellido'],
                    'telefono': visitante_data['telefono'],
                    'correo': visitante_data['correo'],
                    'edad': visitante_data['edad']
                }
            )

            # Procesar acompañantes
            acompanantes = []
            i = 1
            while f'acompanante_rut_{i}' in request.POST:
                # Omitiendo el código de acompañantes para brevedad, asumiendo que funciona
                i += 1
            
            cantidad_visitantes = int(request.POST.get('cantidadVisitantes', 1)) # Usar un campo oculto o calcular

            disponibilidad_id = request.POST.get('hora')
            disponibilidad = DisponibilidadParque.objects.get(id=disponibilidad_id)

            if disponibilidad.capacidadActual + cantidad_visitantes > disponibilidad.capacidadMaxima:
                messages.error(request, 'No hay suficiente capacidad para la cantidad de visitantes')
                return redirect('form')

            tipo_visita_nombre = request.POST.get('tipoVisita')
            tipo_visita = TipoVisita.objects.get(nombre=tipo_visita_nombre)

            reserva = Reserva.objects.create(
                visitante=visitante,
                disponibilidad=disponibilidad,
                cantidadVisitantes=cantidad_visitantes,
                tipoVisita=tipo_visita,
                estadoReserva=Reserva.Estado.ACTIVO
            )

            disponibilidad.capacidadActual += cantidad_visitantes
            disponibilidad.save()

            messages.success(request, 'Reserva creada exitosamente')
            crear_notificacion('Reserva Creada', f'Reserva {reserva.idReserva} creada para {visitante.nombre}.')
            return redirect('inicio')

        except Exception as e:
            messages.error(request, f'Error al procesar la reserva: {str(e)}')
            return redirect('form')

    return redirect('form')

def validarReserva(request):
    # ... (código existente para validar reserva) ...
    # Obtener parámetros de filtro
    fecha = request.GET.get('fecha')
    estado = request.GET.get('estado')
    page_number = request.GET.get('page', 1)
    
    # Construir query base con los nombres correctos de tablas y columnas
    query = """
        SELECT 
            r.idReserva,
            r.visitante_id as visitante_rut,
            r.disponibilidad_id,
            r.cantidadVisitantes,
            r.tipoVisita_id,
            r.estadoReserva,
            v.nombre as visitante_nombre,
            v.apellido as visitante_apellido,
            v.telefono as visitante_telefono,
            v.correo as visitante_correo,
            d.fecha as disponibilidad_fecha,
            d.horaInicio,
            d.horaFin,
            tv.nombre as tipo_visita_nombre
        FROM reserva r
        INNER JOIN visitante v ON r.visitante_id = v.rut
        INNER JOIN disponibilidadParque d ON r.disponibilidad_id = d.id
        INNER JOIN tipoVisita tv ON r.tipoVisita_id = tv.nombre
        WHERE 1=1
    """
    
    params = []
    
    # Aplicar filtros
    if fecha:
        query += " AND d.fecha = %s"
        params.append(fecha)
    
    if estado:
        query += " AND r.estadoReserva = %s"
        params.append(estado)
    
    # Ordenar por ID de reserva descendente
    query += " ORDER BY r.idReserva DESC"
    
    with connection.cursor() as cursor:
        # Ejecutar query principal
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        reservas_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        # Para cada reserva, obtener los acompañantes
        for reserva in reservas_data:
            # Nota: Usamos 'acompañante' en minúscula y sin tilde en SQL si la tabla se creó así
            # Basado en models.py, debería ser 'acompañante'
            cursor.execute("""
                SELECT rut, nombre, edad 
                FROM acompañante 
                WHERE rutVisitante_id = %s
            """, [reserva['visitante_rut']])
            
            acompanantes_columns = [col[0] for col in cursor.description]
            reserva['acompanantes'] = [
                dict(zip(acompanantes_columns, row)) 
                for row in cursor.fetchall()
            ]
    
    # Paginación
    paginator = Paginator(reservas_data, 10)  # 10 reservas por página
    page_obj = paginator.get_page(page_number)
    
    context = {
        'reservas': page_obj,
        'filtros': {
            'fecha': fecha,
            'estado': estado
        }
    }
    
    return render(request, 'reservas.html', context)
# ... (código existente para confirmar_reserva y cancelar_reserva - no mostrado por brevedad) ...

# --- Vistas para el Módulo de Reajuste ---

def modificarReserva(request, reserva_id):
    """Muestra el formulario para modificar una reserva existente (interfaz de modificación)."""
    reserva = get_object_or_404(Reserva, idReserva=reserva_id)
    
    # Obtener opciones para el formulario de modificación
    disponibilidades = DisponibilidadParque.objects.all().order_by('fecha', 'horaInicio')
    tipos_visita = TipoVisita.objects.all().order_by('nombre')
    
    # Opcional: obtener acompañantes (si se permite modificar la cantidad de visitantes)
    acompanantes = Acompañante.objects.filter(rutVisitante=reserva.visitante)
    
    context = {
        'reserva': reserva,
        'disponibilidades': disponibilidades,
        'tipos_visita': tipos_visita,
        'acompanantes': acompanantes,
        'cantidad_acompanantes': acompanantes.count(),
    }
    return render(request, 'modificar_reserva.html', context)

@transaction.atomic
def guardarModificacionReserva(request, reserva_id):
    """Procesa la modificación de la reserva (control de disponibilidad y registro de cambios)."""
    reserva = get_object_or_404(Reserva, idReserva=reserva_id)

    if request.method == 'POST':
        try:
            old_disponibilidad = reserva.disponibilidad
            old_cantidad_visitantes = reserva.cantidadVisitantes
            old_tipo_visita = reserva.tipoVisita

            # 1. Obtener nuevos datos del formulario
            new_disponibilidad_id = request.POST.get('hora')
            new_tipo_visita_nombre = request.POST.get('tipoVisita')
            new_cantidad_visitantes = int(request.POST.get('cantidadVisitantes')) # Asumiendo que se envía en un campo oculto o se calcula en la plantilla
            
            new_disponibilidad = DisponibilidadParque.objects.get(id=new_disponibilidad_id)
            new_tipo_visita = TipoVisita.objects.get(nombre=new_tipo_visita_nombre)
            
            # 2. Revertir capacidad de la disponibilidad antigua
            if old_disponibilidad:
                old_disponibilidad.capacidadActual -= old_cantidad_visitantes
                old_disponibilidad.save()

            # 3. Verificar y aplicar nueva capacidad (Control de Disponibilidad)
            capacidad_requerida = new_cantidad_visitantes
            capacidad_disponible = new_disponibilidad.capacidadMaxima - new_disponibilidad.capacidadActual

            if capacidad_requerida > capacidad_disponible:
                # 3a. Revertir cambios si la nueva capacidad es insuficiente
                old_disponibilidad.capacidadActual += old_cantidad_visitantes
                old_disponibilidad.save()
                messages.error(request, 'ERROR: La nueva disponibilidad seleccionada no tiene capacidad suficiente.')
                return redirect('modificar_reserva', reserva_id=reserva_id)

            # 4. Actualizar la reserva
            reserva.disponibilidad = new_disponibilidad
            reserva.cantidadVisitantes = new_cantidad_visitantes
            reserva.tipoVisita = new_tipo_visita
            reserva.save()

            # 5. Aplicar la nueva capacidad
            new_disponibilidad.capacidadActual += new_cantidad_visitantes
            new_disponibilidad.save()

            # 6. Registrar el cambio (Registro de Cambios)
            descripcion = f"Modificación. Fecha/Hora de {old_disponibilidad} a {new_disponibilidad}. Tipo de {old_tipo_visita.nombre} a {new_tipo_visita.nombre}. Cantidad de {old_cantidad_visitantes} a {new_cantidad_visitantes} visitantes."
            RegistroCambioReserva.objects.create(
                reserva=reserva,
                usuario='Administrador', # Se puede cambiar por el usuario logueado o 'Visitante'
                descripcionCambio=descripcion
            )
            
            # 7. Sistema de Notificación
            crear_notificacion('Reserva Modificada', f'Reserva {reserva_id} reajustada por el administrador.')

            messages.success(request, f'La reserva {reserva_id} ha sido modificada exitosamente.')
            return redirect('validar_reserva') # Redirigir a la lista de validación

        except Exception as e:
            # Revertir cualquier cambio de capacidad si falla
            try:
                if 'old_disponibilidad' in locals():
                    old_disponibilidad.capacidadActual += old_cantidad_visitantes
                    old_disponibilidad.save()
            except Exception:
                pass # Ignorar errores de reversión si fallan

            messages.error(request, f'Error al guardar la modificación: {str(e)}')
            return redirect('modificar_reserva', reserva_id=reserva_id)
            
    return redirect('validar_reserva')

