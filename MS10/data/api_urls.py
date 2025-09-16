from django.urls import path
from .views import FileListCreateAPIView, FileDetailAPIView

urlpatterns = [
    path('projects/<uuid:project_id>/files/', FileListCreateAPIView.as_view(), name='file-list-create'),
    path('files/<uuid:pk>/', FileDetailAPIView.as_view(), name='file-detail'),
]