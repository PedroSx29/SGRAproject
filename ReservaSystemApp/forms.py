from django import forms
from ReservaSystemApp.models import Reserva

# class ReservaForm(forms.ModelForm):
#     class Meta:
#         model = Reserva
#         fields = '__all__'
#         widgets = {
#             'visitante': forms.TextInput(attrs={'class': 'form-control'}),
#             'Apellido': forms.TextInput(attrs={'class': 'form-control'}),
#             'Fecha de Reserva': forms.Select(attrs={'class': 'form-select'}),
#             'Hora de Reserva': forms.Select(attrs={'class': 'form-select'}),
#     }
