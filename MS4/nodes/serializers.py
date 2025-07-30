# in nodes/serializers.py

from rest_framework import serializers
from .models import Node

class NodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Node
        fields = ['id', 'project_id', 'owner_id', 'name', 'configuration', 'created_at', 'updated_at']
        read_only_fields = fields

class NodeCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=True)
    configuration = serializers.JSONField(required=True)

    def validate_configuration(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Configuration must be a valid JSON object.")
        if "node_type" not in value:
            raise serializers.ValidationError("Configuration must include a 'node_type'.")
        if "model_config" not in value or "model_id" not in value["model_config"]:
            raise serializers.ValidationError("Configuration must include 'model_config' with a 'model_id'.")
        return value

class NodeUpdateSerializer(NodeCreateSerializer):
    # Inherits all fields and validation from the create serializer.
    pass