from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('ms3/api/v1/', include('aimodels.urls')),

    # Internal API for MS3
    path('ms3/internal/v1/', include('aimodelsinternal.internal_urls')),
]