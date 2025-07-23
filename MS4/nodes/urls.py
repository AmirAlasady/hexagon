# in nodes/urls.py

from django.urls import path
from .views import NodeListCreateAPIView, NodeDetailAPIView

app_name = 'nodes'

urlpatterns = [

    path(
        'projects/<uuid:project_id>/nodes/', 
        NodeListCreateAPIView.as_view(), 
        name='node-list-create'
    ),

    path(
        'nodes/<uuid:pk>/', 
        NodeDetailAPIView.as_view(), 
        name='node-detail'
    ),
]