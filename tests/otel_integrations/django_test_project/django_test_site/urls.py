from django.contrib import admin
from django.urls import include, path  # type: ignore

from tests.otel_integrations.django_test_project.django_test_app.views import ninja_api

urlpatterns = [
    path('django_test_app/', include('django_test_app.urls')),
    path('ninja/', ninja_api.urls),
    path('admin/', admin.site.urls),
]
