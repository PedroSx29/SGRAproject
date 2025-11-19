from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db import connection
from ReservaSystemApp.models import DisponibilidadParque, Visitante, Acompañante, Reserva, TipoVisita

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
            print("Datos recibidos del formulario:", request.POST)  # Debug

            # Obtener datos del visitante principal
            visitante_data = {
                'rut': request.POST.get('rut'),
                'nombre': request.POST.get('nombre'),
                'telefono': request.POST.get('telefono'),
                'correo': request.POST.get('correo'),
                'edad': int(request.POST.get('edad')),
                'apellido': ''  # Campo requerido en el modelo
            }

            print("Datos del visitante:", visitante_data)  # Debug

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

            print("Visitante creado/actualizado:", visitante.rut)  # Debug

            # Procesar acompañantes
            acompanantes = []
            i = 1
            while f'acompanante_rut_{i}' in request.POST:
                acompanante_data = {
                    'rut': request.POST.get(f'acompanante_rut_{i}'),
                    'nombre': request.POST.get(f'acompanante_nombre_{i}'),
                    'edad': int(request.POST.get(f'acompanante_edad_{i}', 0))
                }
                
                if acompanante_data['rut'] and acompanante_data['nombre']:
                    acompanante = Acompañante.objects.create(
                        rut=acompanante_data['rut'],
                        rutVisitante=visitante,
                        nombre=acompanante_data['nombre'],
                        edad=acompanante_data['edad']
                    )
                    acompanantes.append(acompanante)
                    print(f"Acompañante {i} creado:", acompanante.rut)  # Debug
                i += 1

            # Calcular cantidad total de visitantes
            cantidad_visitantes = len(acompanantes) + 1  # Acompañantes + visitante principal
            print("Cantidad total de visitantes:", cantidad_visitantes)  # Debug

            # Obtener disponibilidad seleccionada
            disponibilidad_id = request.POST.get('hora')
            print("ID de disponibilidad seleccionada:", disponibilidad_id)  # Debug
            
            disponibilidad = DisponibilidadParque.objects.get(id=disponibilidad_id)
            print("Disponibilidad encontrada:", disponibilidad)  # Debug

            # Verificar si hay capacidad suficiente
            if disponibilidad.capacidadActual + cantidad_visitantes > disponibilidad.capacidadMaxima:
                messages.error(request, 'No hay suficiente capacidad para la cantidad de visitantes')
                return redirect('form')

            # Obtener el tipo de visita
            tipo_visita_nombre = request.POST.get('tipoVisita')
            print("Tipo de visita seleccionado:", tipo_visita_nombre)  # Debug
            
            tipo_visita = TipoVisita.objects.get(nombre=tipo_visita_nombre)
            print("Tipo de visita encontrado:", tipo_visita)  # Debug

            # Crear la reserva
            reserva = Reserva.objects.create(
                visitante=visitante,
                disponibilidad=disponibilidad,
                cantidadVisitantes=cantidad_visitantes,
                tipoVisita=tipo_visita,
                estadoReserva=Reserva.Estado.ACTIVO
            )

            print("Reserva creada:", reserva.idReserva)  # Debug

            # Actualizar la capacidad actual del parque
            disponibilidad.capacidadActual += cantidad_visitantes
            disponibilidad.save()
            print("Capacidad actualizada. Nueva capacidad:", disponibilidad.capacidadActual)  # Debug

            messages.success(request, 'Reserva creada exitosamente')
            return redirect('inicio')

        except Exception as e:
            print("Error al procesar la reserva:", str(e))  # Debug
            messages.error(request, f'Error al procesar la reserva: {str(e)}')
            return redirect('form')

    return redirect('form')

def validarReserva(request):
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