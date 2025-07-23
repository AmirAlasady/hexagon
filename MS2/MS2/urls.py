
from django.contrib import admin
from django.urls import path, include



urlpatterns = [
    path('admin/', admin.site.urls),

    path('ms2/api/v1/', include('project.urls')),


    # internal API 
    path('ms2/internal/v1/', include('projectsinternal.internal_urls')),
]

