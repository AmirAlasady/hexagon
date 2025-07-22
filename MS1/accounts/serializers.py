# accounts/serializers.py
from djoser.serializers import (
    UserCreateSerializer as BaseUserCreateSerializer,
    UserSerializer as BaseUserSerializer,
    SetPasswordSerializer as BaseSetPasswordSerializer
)
from rest_framework import serializers

from django.contrib.auth import get_user_model

User = get_user_model()


from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
# from rest_framework_simplejwt.tokens import RefreshToken # Not strictly needed for this change

# this iwll make ue customize the serilizer to customize the token
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user) # Gets the default claims (user_id, exp, jti)

        # Add custom claims
        token['username'] = user.username # Example: good to have username
        token['email'] = user.email     # Example: if MS2 might need it without another call
        token['is_staff'] = user.is_staff # <<< CRITICAL: Add the is_staff status

        # You could add other claims here if needed, e.g.,
        # token['first_name'] = user.first_name
        # token['roles'] = list(user.groups.values_list('name', flat=True)) # If using Django groups as roles
        return token

class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        model = User
        fields = ['id', 'email', 'username', 'password']
        
    def validate(self, attrs):
        # This ensures validation happens correctly
        attrs = super().validate(attrs)
        # Print validation info
        print(f"VALIDATION ATTRS: {attrs}")
        return attrs
        
    def create(self, validated_data):
        user = super().create(validated_data)
        return user

# --- User Serializer for Djoser's general user endpoints ---
class UserSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = ['id', 'email', 'username', 'is_active']
        read_only_fields = ['id', 'email', 'is_active']


# --- Specific Action Serializers ---
class CurrentPasswordMixin(serializers.Serializer):
    current_password = serializers.CharField(style={'input_type': 'password'}, write_only=True)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

class EmailChangeSerializer(CurrentPasswordMixin, serializers.Serializer):
    new_email = serializers.EmailField()

    def validate_new_email(self, value):
        user = self.context['request'].user
        if User.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This email is already in use by another account.")
        return value

class UsernameChangeSerializer(CurrentPasswordMixin, serializers.Serializer):
    new_username = serializers.CharField(max_length=User._meta.get_field('username').max_length)

    def validate_new_username(self, value):
        user = self.context['request'].user
        if User.objects.filter(username__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("This username is already in use.")
        return value