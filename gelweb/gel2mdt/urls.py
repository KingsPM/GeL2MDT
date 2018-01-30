from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register, name='register'),
    path('rare-disease-main', views.rare_disease_main, name='rare-disease-main'),
    path('cancer-main', views.cancer_main, name='cancer-main'),
]