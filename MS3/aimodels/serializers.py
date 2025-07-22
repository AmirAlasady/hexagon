from rest_framework import serializers
from .models import AIModel

class AIModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModel
        fields = ['id', 'name', 'provider', 'is_system_model', 'owner_id', 'configuration', 'capabilities']
        read_only_fields = ['id', 'owner_id', 'is_system_model']
        
    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if not instance.is_system_model:
            sanitized_config = {key: "******" for key in ret.get('configuration', {}).keys()}
            ret['configuration'] = sanitized_config
        return ret

class AIModelCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=True)
    provider = serializers.CharField(max_length=100, required=True)
    configuration = serializers.JSONField(required=True)

class AIModelUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=True)
    configuration = serializers.JSONField(required=True)