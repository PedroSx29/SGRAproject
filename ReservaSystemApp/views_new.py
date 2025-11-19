from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from ReservaSystemApp.models import DisponibilidadParque, Visitante, Acompañante, Reserva, TipoVisita
from django.utils import timezone

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

def listar_reservas(request):
    # Obtener filtros
    fecha = request.GET.get('fecha')
    estado = request.GET.get('estado')

    # Consulta base
    reservas = Reserva.objects.all().order_by('-disponibilidad__fecha', '-disponibilidad__horaInicio')

    # Aplicar filtros
    if fecha:
        reservas = reservas.filter(disponibilidad__fecha=fecha)
    if estado:
        reservas = reservas.filter(estadoReserva=estado)

    # Paginación
    paginator = Paginator(reservas, 10)  # 10 reservas por página
    page = request.GET.get('page')
    reservas = paginator.get_page(page)

    context = {
        'reservas': reservas,
    }
    return render(request, 'reservas.html', context)

@transaction.atomic
def confirmar_reserva(request, reserva_id):
    if request.method == 'POST':
        reserva = get_object_or_404(Reserva, idReserva=reserva_id)
        if reserva.estadoReserva == Reserva.Estado.ACTIVO:
            reserva.estadoReserva = Reserva.Estado.UTILIZADO
            reserva.save()
            messages.success(request, 'Reserva confirmada exitosamente')
        else:
            messages.error(request, 'La reserva no puede ser confirmada en su estado actual')
    return redirect('listar_reservas')

@transaction.atomic
def cancelar_reserva(request, reserva_id):
    if request.method == 'POST':
        reserva = get_object_or_404(Reserva, idReserva=reserva_id)
        if reserva.estadoReserva == Reserva.Estado.ACTIVO:
            # Liberar la capacidad del parque
            disponibilidad = reserva.disponibilidad
            disponibilidad.capacidadActual -= reserva.cantidadVisitantes
            disponibilidad.save()
            
            # Cambiar estado de la reserva
            reserva.estadoReserva = 'CANCELADO'
            reserva.save()
            
            messages.success(request, 'Reserva cancelada exitosamente')
        else:
            messages.error(request, 'La reserva no puede ser cancelada en su estado actual')
    return redirect('listar_reservas')