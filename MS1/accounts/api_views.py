# accounts/api_views.py
from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView


from .serializers import (
    EmailChangeSerializer,
    UsernameChangeSerializer,
)



class EmailChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = EmailChangeSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            new_email = serializer.validated_data['new_email']
            user.email = new_email
            user.save(update_fields=['email'])
            return Response({"detail": "Login email changed successfully. You may need to log in again with the new email."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UsernameChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = UsernameChangeSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            user.username = serializer.validated_data['new_username']
            user.save(update_fields=['username'])
            return Response({"detail": "Username changed successfully."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

