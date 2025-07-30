# in aimodels/services.py (Corrected and Final Version)

from django.db.models import Q
from .models import AIModel
from rest_framework.exceptions import ValidationError, PermissionDenied
import jsonschema

# --- Placeholder Encryption (as before) ---
def encrypt_values(raw_values: dict, schema: dict) -> dict:
    encrypted = {}
    for key, value in raw_values.items():
        if schema.get('properties', {}).get(key, {}).get('sensitive'):
            encrypted[key] = f"ENCRYPTED({value[::-1]})"
        else:
            encrypted[key] = value
    return encrypted

# --- The Final Service Class ---
class AIModelService:
    def get_available_models_for_user(self, user_id):
        """ Returns all system models + the user's own private models. """
        return AIModel.objects.filter(
            Q(is_system_model=True) | Q(owner_id=user_id)
        )

    def get_model_by_id(self, model_id, user_id):
        """
        Retrieves a single model, ensuring the user has permission to view it.
        (A user can view any system model or their own models).
        """
        try:
            model = AIModel.objects.get(id=model_id)
        except AIModel.DoesNotExist:
            raise ValidationError("Model not found.") # This will result in a 404/400

        # --- THE CRITICAL FIX IS HERE ---
        # If it's a system model, anyone can view it.
        # If it's NOT a system model, the owner_id MUST match the user_id.
        is_owner = str(model.owner_id) == str(user_id)
        
        if not model.is_system_model and not is_owner:
            raise PermissionDenied("You do not have permission to access this model.")
            
        return model

    def create_user_model(self, *, owner_id, name, provider, configuration):
        """ Creates a new private model configuration for a user. """
        # (This method was already correct, but we include it for completeness)
        try:
            blueprint = AIModel.objects.get(provider=provider, is_system_model=True)
        except AIModel.DoesNotExist:
            raise ValidationError(f"No system model template found for provider '{provider}'.")
            
        schema = blueprint.configuration
        try:
            jsonschema.validate(instance=configuration, schema=schema)
        except jsonschema.ValidationError as e:
            raise ValidationError(f"Configuration is invalid for '{provider}': {e.message}")
            
        encrypted_config = encrypt_values(configuration, schema)
        
        user_model = AIModel.objects.create(
            is_system_model=False,
            owner_id=owner_id,
            name=name,
            provider=provider,
            configuration=encrypted_config,
            capabilities=blueprint.capabilities
        )
        return user_model

    def update_user_model(self, *, model_id, user_id, name, configuration):
        """ Updates a user's private model configuration. """
        # Step 1: Get the model. get_model_by_id already performs the necessary view permission check.
        model_to_update = self.get_model_by_id(model_id, user_id)
        
        # Step 2: Add an explicit check to prevent updating system models.
        if model_to_update.is_system_model:
            raise PermissionDenied("System models cannot be modified.")
            
        # Step 3: Proceed with validation and update logic
        blueprint = AIModel.objects.get(provider=model_to_update.provider, is_system_model=True)
        schema = blueprint.configuration
        try:
            jsonschema.validate(instance=configuration, schema=schema)
        except jsonschema.ValidationError as e:
            raise ValidationError(f"Configuration is invalid: {e.message}")
            
        model_to_update.name = name
        model_to_update.configuration = encrypt_values(configuration, schema)
        model_to_update.save()
        return model_to_update

    def delete_user_model(self, *, model_id, user_id):
        """ Deletes a user's private model configuration. """
        model_to_delete = self.get_model_by_id(model_id, user_id)
        
        if model_to_delete.is_system_model:
             raise PermissionDenied("System models cannot be deleted.")
             
        model_to_delete.delete()
        # No return value needed for a successful delete.