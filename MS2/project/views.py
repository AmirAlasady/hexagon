from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import Project
from .serializers import ProjectSerializer, ProjectCreateSerializer
from .permissions import IsOwner

class ProjectListCreateAPIView(generics.ListCreateAPIView):
    """
    API view to retrieve a list of projects or create a new project.
    * GET: Returns a list of projects owned by the authenticated user.
    * POST: Creates a new project owned by the authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        # This remains the same. It correctly selects the serializer
        # for validating the *input* data on a POST.
        if self.request.method == 'POST':
            return ProjectCreateSerializer
        return ProjectSerializer

    def get_queryset(self):
        """
        This view should return a list of all the projects
        for the currently authenticated user.
        """
        user = self.request.user
        return Project.objects.filter(owner_id=user.id)

    # We are replacing perform_create with a full override of the create method.
    def create(self, request, *args, **kwargs):
        """
        Custom create method to use different serializers for input and output.
        """
        # 1. Use the "Create" serializer to validate the incoming request data.
        write_serializer = self.get_serializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        
        # 2. Call our custom perform_create logic to save the object.
        # This is where we inject the owner_id.
        instance = self.perform_create(write_serializer)
        
        # 3. Use the more detailed "ProjectSerializer" to create the response data.
        read_serializer = ProjectSerializer(instance)
        
        # 4. Manually construct the 201 Created response.
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        """
        Saves the new instance with the owner_id.
        This method now returns the created instance so the `create` method can use it.
        """
        # The serializer is already validated at this point.
        return serializer.save(owner_id=self.request.user.id)


class ProjectDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    # This view remains unchanged, it is already correct.
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    serializer_class = ProjectSerializer
    queryset = Project.objects.all()