
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('ms4/api/v1/', include('nodes.urls')),  # API-based auth
]
