from rest_framework import serializers
from .models import Node

class NodeSerializer(serializers.ModelSerializer):
    """
    The primary, read-only serializer for displaying Node objects.
    Used for all GET requests (list and detail).
    """
    class Meta:
        model = Node
        fields = [
            'id', 'project_id', 'owner_id', 'name', 'status', 
            'configuration', 'created_at', 'updated_at'
        ]
        read_only_fields = fields # Make all fields read-only by default

class NodeDraftCreateSerializer(serializers.Serializer):
    """
    Used ONLY for the STAGE 1 `POST /nodes/draft/` endpoint.
    Strictly validates only the name and project_id, ignoring all other fields.
    """
    name = serializers.CharField(max_length=255, required=True)
    project_id = serializers.UUIDField(required=True)

class NodeConfigureModelSerializer(serializers.Serializer):
    """
    Used ONLY for the STAGE 2 `POST /nodes/{pk}/configure-model/` endpoint.
    Validates only the model_id.
    """
    model_id = serializers.UUIDField(required=True)

class NodeUpdateSerializer(serializers.Serializer):
    """
    Used for the final `PUT /nodes/{pk}/` endpoint after a node is active.
    Allows the user to update the name and the filled-out configuration.
    """
    name = serializers.CharField(max_length=255, required=True)
    configuration = serializers.JSONField(required=True)