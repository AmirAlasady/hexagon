from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('ms1/api/v1/auth/', include('accounts.api_urls')),
]