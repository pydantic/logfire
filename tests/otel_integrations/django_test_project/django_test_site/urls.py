from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('django_test_app/', include('django_test_app.urls')),
    path('admin/', admin.site.urls),
]
