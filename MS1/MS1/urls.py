
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from .views import protected_media_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('ms1/api/v1/auth/', include('accounts.api_urls')),  # API-based auth
]

