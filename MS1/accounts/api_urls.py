# accounts/api_urls.py
from django.urls import include, path
from .api_views import (
    EmailChangeView,
    UsernameChangeView, 
)

# Define custom urlpatterns first for clarity
custom_urlpatterns = [
    path('account/change-email/', EmailChangeView.as_view(), name='api-account-change-email'),
    path('account/change-username/', UsernameChangeView.as_view(), name='api-account-change-username'),
]

urlpatterns = [
    # Djoser core endpoints
    path('', include('djoser.urls')),
    # Djoser JWT endpoints
    path('', include('djoser.urls.jwt')),
    # Your custom endpoints
    path('', include(custom_urlpatterns)),
]