from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator
from django.db import connection
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from decimal import Decimal 
from ReservaSystemApp.models import (
    DisponibilidadParque, Visitante, Acompañante, Reserva, TipoVisita,
    RegistroCambioReserva, SistemaNotificaciones
)

# Create your views here.
def crear_notificacion(tipo, mensaje):
    SistemaNotificaciones.objects.create(
        fechaEnvio=timezone.now().date(),
        tipo=tipo,
        mensaje=mensaje
    )

def mostrarTipoVisita(request):
    tipos_visita = TipoVisita.objects.all().order_by('nombre')
    context = {
        'tipos_visita': tipos_visita
    }
    return render(request, 'form.html', context)

def inicio(request):
    return render(request, 'index.html')

def form(request):
    return mostrarDisponibilidad(request)

def mostrarDisponibilidad(request):
    try:
        disponibilidades = DisponibilidadParque.objects.all().order_by('fecha', 'horaInicio')
        
        for disp in disponibilidades:
            disp.cupos_disponibles = disp.capacidadMaxima - disp.capacidadActual
        
        tipos_visita = TipoVisita.objects.all().order_by('nombre')
        
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
            visitante_data = {
                'rut': request.POST.get('rut'),
                'nombre': request.POST.get('nombre'),
                'apellido': request.POST.get('apellido'), 
                'telefono': request.POST.get('telefono'),
                'correo': request.POST.get('correo'),
                'fecha_nacimiento': request.POST.get('fecha_nacimiento'), 
            }

            visitante = Visitante.objects.create(
                rut=visitante_data['rut'],
                nombre=visitante_data['nombre'],
                apellido=visitante_data['apellido'],
                telefono=visitante_data['telefono'],
                correo=visitante_data['correo'],
                fecha_nacimiento=visitante_data['fecha_nacimiento']
            )

            cantidad_visitantes = 1
            i = 1
            while f'acompanante_rut_{i}' in request.POST:
                acompanante_data = {
                    'rut': request.POST.get(f'acompanante_rut_{i}'),
                    'nombre': request.POST.get(f'acompanante_nombre_{i}'),
                    'fecha_nacimiento': request.POST.get(f'acompanante_fecha_nacimiento_{i}'), 
                }
                
                if acompanante_data['rut'] and acompanante_data['nombre'] and acompanante_data['fecha_nacimiento']:
                    Acompañante.objects.create(
                        rut=acompanante_data['rut'],
                        rutVisitante=visitante,
                        nombre=acompanante_data['nombre'],
                        fecha_nacimiento=acompanante_data['fecha_nacimiento']
                    )
                    cantidad_visitantes += 1
                i += 1
            
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

@login_required 
def validarReserva(request):
    fecha = request.GET.get('fecha')
    estado = request.GET.get('estado')
    page_number = request.GET.get('page', 1)
    
    query = """
        SELECT 
            r.idReserva,
            r.visitante_id,              
            v.rut as visitante_rut,      
            v.fecha_nacimiento as visitante_fecha_nacimiento,
            r.disponibilidad_id,
            r.cantidadVisitantes,
            r.estadoReserva,
            v.nombre as visitante_nombre,
            v.apellido as visitante_apellido,
            v.telefono as visitante_telefono,
            v.correo as visitante_correo,
            d.fecha as disponibilidad_fecha,
            d.horaInicio,
            d.horaFin,
            r.tipoVisita_id as tipo_visita_nombre
        FROM reserva r
        INNER JOIN visitante v ON r.visitante_id = v.idVisitante
        INNER JOIN disponibilidadParque d ON r.disponibilidad_id = d.id
        WHERE 1=1
    """
    
    params = []
    
    if fecha:
        query += " AND d.fecha = %s"
        params.append(fecha)
    
    if estado:
        query += " AND r.estadoReserva = %s"
        params.append(estado)
    
    query += " ORDER BY r.idReserva DESC"
    
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        reservas_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        for reserva in reservas_data:
            visitante_pk_id = reserva['visitante_id'] 
            
            cursor.execute("""
                SELECT rut, nombre, fecha_nacimiento /* CAMBIO: Reemplazado 'edad' por 'fecha_nacimiento' */
                FROM acompañante 
                WHERE rutVisitante_id = %s 
            """, [visitante_pk_id])
            
            acompanantes_columns = [col[0] for col in cursor.description]
            reserva['acompanantes'] = [
                dict(zip(acompanantes_columns, row)) 
                for row in cursor.fetchall()
            ]

    
    paginator = Paginator(reservas_data, 10)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'reservas': page_obj,
        'filtros': {
            'fecha': fecha,
            'estado': estado
        }
    }
    
    return render(request, 'reservas.html', context)

@login_required 
def modificarReserva(request, reserva_id):
    reserva = get_object_or_404(Reserva, idReserva=reserva_id)
    
    disponibilidades = DisponibilidadParque.objects.all().order_by('fecha', 'horaInicio')
    tipos_visita = TipoVisita.objects.all().order_by('nombre')
    
    acompanantes = Acompañante.objects.filter(rutVisitante=reserva.visitante)
    
    context = {
        'reserva': reserva,
        'disponibilidades': disponibilidades,
        'tipos_visita': tipos_visita,
        'acompanantes': acompanantes,
        'cantidad_acompanantes': acompanantes.count(),
    }
    return render(request, 'modificar_reserva.html', context)

@login_required 
@transaction.atomic
def guardarModificacionReserva(request, reserva_id):
    reserva = get_object_or_404(Reserva, idReserva=reserva_id)

    if request.method == 'POST':
        try:
            old_disponibilidad = reserva.disponibilidad
            old_cantidad_visitantes = reserva.cantidadVisitantes
            old_tipo_visita = reserva.tipoVisita

            new_disponibilidad_id = request.POST.get('hora')
            new_tipo_visita_nombre = request.POST.get('tipoVisita')
            new_cantidad_visitantes = old_cantidad_visitantes 
            
            new_disponibilidad = DisponibilidadParque.objects.get(id=new_disponibilidad_id)
            new_tipo_visita = TipoVisita.objects.get(nombre=new_tipo_visita_nombre)
            
            if old_disponibilidad:
                old_disponibilidad.capacidadActual -= old_cantidad_visitantes
                old_disponibilidad.save()

            capacidad_requerida = new_cantidad_visitantes
            capacidad_disponible = new_disponibilidad.capacidadMaxima - new_disponibilidad.capacidadActual

            if capacidad_requerida > capacidad_disponible:
                old_disponibilidad.capacidadActual += old_cantidad_visitantes
                old_disponibilidad.save()
                messages.error(request, 'ERROR: La nueva disponibilidad seleccionada no tiene capacidad suficiente.')
                return redirect('modificar_reserva', reserva_id=reserva_id)

            reserva.disponibilidad = new_disponibilidad
            reserva.cantidadVisitantes = new_cantidad_visitantes
            reserva.tipoVisita = new_tipo_visita
            reserva.save()

            new_disponibilidad.capacidadActual += new_cantidad_visitantes
            new_disponibilidad.save()

            descripcion = f"Modificación. Fecha/Hora de {old_disponibilidad} a {new_disponibilidad}. Tipo de {old_tipo_visita.nombre} a {new_tipo_visita.nombre}. Cantidad de {old_cantidad_visitantes} a {new_cantidad_visitantes} visitantes."
            RegistroCambioReserva.objects.create(
                reserva=reserva,
                usuario='Administrador',
                descripcionCambio=descripcion
            )
            
            crear_notificacion('Reserva Modificada', f'Reserva {reserva_id} reajustada por el administrador.')

            messages.success(request, f'La reserva {reserva_id} ha sido modificada exitosamente.')
            return redirect('validar_reserva')

        except Exception as e:
            try:
                if 'old_disponibilidad' in locals():
                    old_disponibilidad.capacidadActual += old_cantidad_visitantes
                    old_disponibilidad.save()
            except Exception:
                pass

            messages.error(request, f'Error al guardar la modificación: {str(e)}')
            return redirect('modificar_reserva', reserva_id=reserva_id)
            
    return redirect('validar_reserva')

@login_required 
def dashboardMonitoreo(request):
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    tipo_visita_filtro = request.GET.get('tipo_visita')
    
    reservas_base = Reserva.objects.filter(estadoReserva__in=[Reserva.Estado.ACTIVO, Reserva.Estado.UTILIZADO])
    
    if fecha_inicio:
        reservas_base = reservas_base.filter(disponibilidad__fecha__gte=fecha_inicio)
    if fecha_fin:
        reservas_base = reservas_base.filter(disponibilidad__fecha__lte=fecha_fin)
    if tipo_visita_filtro:
        reservas_base = reservas_base.filter(tipoVisita__nombre=tipo_visita_filtro)

    total_reservas = reservas_base.count()
    
    total_visitantes = reservas_base.aggregate(Sum('cantidadVisitantes'))['cantidadVisitantes__sum'] or 0
    
    capacidad_data = DisponibilidadParque.objects.filter(
        fecha__gte=fecha_inicio or '2000-01-01', 
        fecha__lte=fecha_fin or '2999-12-31'
    ).aggregate(Sum('capacidadMaxima'))['capacidadMaxima__sum']
    
    capacidad_agregada = capacidad_data or 0
    
    if capacidad_agregada > 0:
        total_visitantes_dec = Decimal(total_visitantes)
        capacidad_agregada_dec = Decimal(capacidad_agregada)
        
        porcentaje_ocupacion = round((total_visitantes_dec / capacidad_agregada_dec) * 100)
    else:
        porcentaje_ocupacion = 0

    alertas = []
    if porcentaje_ocupacion > 80:
        alertas.append("ALERTA: Ocupación alta. Más del 80% de la capacidad reservada en el período seleccionado.")
        crear_notificacion('ALERTA DE CAPACIDAD', f'Ocupación del parque al {porcentaje_ocupacion}% en el periodo monitoreado.')
    
    if 'generar_informe' in request.GET:
        messages.success(request, f'Informe automático generado. Total de visitantes: {total_visitantes}.')
    
    top_fechas = reservas_base.values(
        'disponibilidad__fecha'
    ).annotate(
        count=Sum('cantidadVisitantes')
    ).order_by('-count')[:5]

    context = {
        'total_reservas': total_reservas,
        'total_visitantes': total_visitantes,
        'porcentaje_ocupacion': porcentaje_ocupacion,
        'top_fechas': top_fechas,
        'tipos_visita': TipoVisita.objects.all().order_by('nombre'),
        'filtros': {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'tipo_visita': tipo_visita_filtro
        },
        'alertas': alertas
    }
    
    return render(request, 'dashboard_monitoreo.html', context)

def login_admin(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user is not None and user.is_active and (user.is_staff or user.is_superuser):
                login(request, user)
                messages.success(request, f"Bienvenido, {username}. Acceso de Administrador concedido.")
                return redirect('dashboard_monitoreo')
            else:
                messages.error(request, "Usuario o contraseña inválidos o el usuario no tiene permisos de administrador.")
        else:
            messages.error(request, "Error en el formulario. Por favor, verifique sus credenciales.")
    else:
        form = AuthenticationForm()

    return render(request, 'login_admin.html', {'form': form})

@login_required 
def logout_admin(request):
    logout(request)
    messages.info(request, "Sesión cerrada exitosamente.")
    return redirect('inicio')