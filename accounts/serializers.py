from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    """Handles user registration with password confirmation."""
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, label='Confirm Password')

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2', 'first_name', 'last_name')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user


class NileTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT serializer that embeds user metadata in the token payload."""
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Embed identifiers directly in the token for downstream API use
        token['username'] = user.username
        token['email'] = user.email
        token['role'] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # Append user info to the login response body as well
        data['username'] = self.user.username
        data['email'] = self.user.email
        data['role'] = self.user.role
        return data


class UserProfileSerializer(serializers.ModelSerializer):
    """Read-only profile serializer for the /api/auth/me/ endpoint."""
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'role', 'created_at', 'last_login')
        read_only_fields = fields
