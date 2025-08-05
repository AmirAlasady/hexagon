from rest_framework import serializers
class InferenceRequestSerializer(serializers.Serializer):
    prompt = serializers.CharField(required=True)