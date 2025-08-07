from django.urls import path
from .internal_views import ModelValidationView, ModelCapabilitiesView

urlpatterns = [
    # For the Node Service to check if a user can use a model
    path('models/<uuid:model_id>/validate', ModelValidationView.as_view(), name='internal-model-validate'),
    
    path('models/<uuid:model_id>/capabilities/', ModelCapabilitiesView.as_view(), name='internal-model-capabilities'),
]