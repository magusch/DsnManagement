from django.urls import path

from . import views

urlpatterns = [
    path('switch/', views.switch_city, name='switch_city'),
]
