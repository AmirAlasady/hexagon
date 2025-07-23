from django.urls import path
from .internal_views import ModelValidationView, ModelConfigurationView

urlpatterns = [
    # For the Node Service to check if a user can use a model
    path('models/<uuid:model_id>/validate', ModelValidationView.as_view(), name='internal-model-validate'),
    
    # For the Inference Orchestrator to get the full, decrypted config
    path('models/<uuid:model_id>/config', ModelConfigurationView.as_view(), name='internal-model-config'),
]