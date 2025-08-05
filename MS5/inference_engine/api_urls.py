from django.urls import path
from .views import InferenceAPIView
urlpatterns = [
    path('nodes/<uuid:node_id>/infer/', InferenceAPIView.as_view(), name='node-infer'),
]