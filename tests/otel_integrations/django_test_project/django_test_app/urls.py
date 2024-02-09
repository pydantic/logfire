from django.urls import path

from . import views

urlpatterns = [
    path('<int:item_id>/', views.detail, name='detail'),
    path('bad/', views.bad, name='bad'),
]
