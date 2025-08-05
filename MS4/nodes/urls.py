# MS4/nodes/urls.py
from django.urls import path
from .views import (
    NodeListAPIView,
    NodeDetailAPIView,
    NodeDraftCreateAPIView,
    NodeConfigureModelAPIView,
    ResourceDeletionHookAPIView
)

app_name = 'nodes'

urlpatterns = [
    # --- WORKFLOW STEP 1: Create a draft node placeholder ---
    path('nodes/draft/', NodeDraftCreateAPIView.as_view(), name='node-draft-create'),
    
    # --- WORKFLOW STEP 2: Configure the draft node with a model ---
    path('nodes/<uuid:pk>/configure-model/', NodeConfigureModelAPIView.as_view(), name='node-configure-model'),

    # --- STANDARD OPERATIONS ---
    # List nodes within a specific project
    path('projects/<uuid:project_id>/nodes/', NodeListAPIView.as_view(), name='node-list'),

    # Manage a single, fully configured node (GET details, PUT updates, DELETE)
    path('nodes/<uuid:pk>/', NodeDetailAPIView.as_view(), name='node-detail'),

    # --- INTERNAL WEBHOOK ---
    # Note: For security, this endpoint is placed under 'api/v1' for now, but in production,
    # you might move all internal routes to a separate URL prefix like '/ms4/internal/v1/'.
    path('hooks/resource-deleted/', ResourceDeletionHookAPIView.as_view(), name='hook-resource-deleted'),
]