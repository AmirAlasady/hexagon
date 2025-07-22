from rest_framework import permissions

class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to perform actions on it.
    """

    def has_object_permission(self, request, view, obj):
  
        if obj.owner_id and request.user and request.user.is_authenticated:
            return str(obj.owner_id) == str(request.user.id)
            
        return False