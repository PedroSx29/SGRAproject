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
from decimal import Decimal # <--- NUEVA IMPORTACIÓN PARA CÁLCULOS PRECISOS
from ReservaSystemApp.models import (
    DisponibilidadParque, Visitante, Acompañante, Reserva, TipoVisita,
    RegistroCambioReserva, SistemaNotificaciones
)

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
        
        # CALCULAR CUPOS DISPONIBLES EN LA VISTA
        for disp in disponibilidades:
            disp.cupos_disponibles = disp.capacidadMaxima - disp.capacidadActual
        
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
            # Obtener datos del visitante principal
            visitante_data = {
                'rut': request.POST.get('rut'),
                'nombre': request.POST.get('nombre'),
                'apellido': request.POST.get('apellido'), 
                'telefono': request.POST.get('telefono'),
                'correo': request.POST.get('correo'),
                'edad': int(request.POST.get('edad')),
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

            # Procesar acompañantes y CALCULAR CANTIDAD TOTAL DE VISITANTES
            cantidad_visitantes = 1  # Inicia con el visitante principal
            i = 1
            while f'acompanante_rut_{i}' in request.POST:
                acompanante_data = {
                    'rut': request.POST.get(f'acompanante_rut_{i}'),
                    'nombre': request.POST.get(f'acompanante_nombre_{i}'),
                    'edad': int(request.POST.get(f'acompanante_edad_{i}', 0))
                }
                
                if acompanante_data['rut'] and acompanante_data['nombre']:
                    # Crear el acompañante
                    Acompañante.objects.create(
                        rut=acompanante_data['rut'],
                        rutVisitante=visitante,
                        nombre=acompanante_data['nombre'],
                        edad=acompanante_data['edad']
                    )
                    cantidad_visitantes += 1  # Sumar al acompañante
                i += 1
            
            disponibilidad_id = request.POST.get('hora')
            disponibilidad = DisponibilidadParque.objects.get(id=disponibilidad_id)

            # VERIFICACIÓN DE CAPACIDAD USANDO EL TOTAL CALCULADO
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

            # ACTUALIZACIÓN DE CAPACIDAD
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
    # ... (código para validar reserva) ...
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
# ... (código existente para confirmar_reserva y cancelar_reserva - omitido por brevedad) ...

# --- Vistas para el Módulo de Reajuste (Admin) ---

@login_required 
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

@login_required 
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
            # La cantidad de visitantes no cambia en la modificación, se reusa el valor original
            new_cantidad_visitantes = old_cantidad_visitantes 
            
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
                usuario='Administrador',
                descripcionCambio=descripcion
            )
            
            # 7. Sistema de Notificación
            crear_notificacion('Reserva Modificada', f'Reserva {reserva_id} reajustada por el administrador.')

            messages.success(request, f'La reserva {reserva_id} ha sido modificada exitosamente.')
            return redirect('validar_reserva')

        except Exception as e:
            # Revertir cualquier cambio de capacidad si falla
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
    # 1. Preparar filtros y datos
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    tipo_visita_filtro = request.GET.get('tipo_visita')
    
    # Base de la consulta: solo reservas activas (o activas/utilizadas)
    reservas_base = Reserva.objects.filter(estadoReserva__in=[Reserva.Estado.ACTIVO, Reserva.Estado.UTILIZADO])
    
    if fecha_inicio:
        reservas_base = reservas_base.filter(disponibilidad__fecha__gte=fecha_inicio)
    if fecha_fin:
        reservas_base = reservas_base.filter(disponibilidad__fecha__lte=fecha_fin)
    if tipo_visita_filtro:
        reservas_base = reservas_base.filter(tipoVisita__nombre=tipo_visita_filtro)

    # 2. Cálculo de Métricas (Dashboard de Visualización)
    total_reservas = reservas_base.count()
    
    # Aseguramos que el resultado de la agregación es un número, o 0 si es None
    total_visitantes = reservas_base.aggregate(Sum('cantidadVisitantes'))['cantidadVisitantes__sum'] or 0
    
    # Capacidad Total del Parque para un rango de fechas
    capacidad_data = DisponibilidadParque.objects.filter(
        fecha__gte=fecha_inicio or '2000-01-01', 
        fecha__lte=fecha_fin or '2999-12-31'
    ).aggregate(Sum('capacidadMaxima'))['capacidadMaxima__sum']
    
    # Aseguramos que capacidad_agregada es un número, o 0 si no hay registros
    capacidad_agregada = capacidad_data or 0
    
    # CÁLCULO DEL PORCENTAJE DE OCUPACIÓN (UTILIZANDO DECIMAL Y VERIFICACIÓN)
    if capacidad_agregada > 0:
        # Convertimos ambos valores a Decimal para una división precisa
        total_visitantes_dec = Decimal(total_visitantes)
        capacidad_agregada_dec = Decimal(capacidad_agregada)
        
        porcentaje_ocupacion = round((total_visitantes_dec / capacidad_agregada_dec) * 100)
    else:
        porcentaje_ocupacion = 0

    # 3. Alertas de Capacidad
    alertas = []
    if porcentaje_ocupacion > 80:
        alertas.append("ALERTA: Ocupación alta. Más del 80% de la capacidad reservada en el período seleccionado.")
        crear_notificacion('ALERTA DE CAPACIDAD', f'Ocupación del parque al {porcentaje_ocupacion}% en el periodo monitoreado.')
    
    # 4. Generación de Informe (Simulado)
    if 'generar_informe' in request.GET:
        # Aquí iría la lógica compleja para generar un PDF o Excel
        messages.success(request, f'Informe automático generado. Total de visitantes: {total_visitantes}.')
    
    # Datos para la tabla de detalle (Top 5 fechas con más visitantes)
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

# --- Funciones de Autenticación (NUEVO) ---

def login_admin(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            # Solo permitir el acceso si el usuario existe Y es un staff/superuser (Administrador)
            if user is not None and user.is_active and (user.is_staff or user.is_superuser):
                login(request, user)
                messages.success(request, f"Bienvenido, {username}. Acceso de Administrador concedido.")
                # Redirige a la URL definida en settings.LOGIN_REDIRECT_URL (dashboard_monitoreo)
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
    # Redirige a la URL definida en settings.LOGOUT_REDIRECT_URL (inicio)
    return redirect('inicio')