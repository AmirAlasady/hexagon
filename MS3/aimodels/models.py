import uuid
from django.db import models

class AIModel(models.Model):
    """
    A single, unified model representing an AI model configuration.
    Can be a global 'System Model' (template) or a private 'User Model'.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    is_system_model = models.BooleanField(
        default=False, 
        db_index=True,
        help_text="True if this is a global model template managed by an admin."
    )
    
    owner_id = models.UUIDField(
        db_index=True, 
        null=True, # A system model has no owner.
        blank=True,
        help_text="The user who owns this configuration. NULL for system models."
    )
    
    name = models.CharField(
        max_length=255, 
        help_text="User-friendly name (e.g., 'My Personal GPT-4o' or 'System Llama 3')."
    )
    
    provider = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Provider identifier (e.g., 'openai', 'ollama', 'anthropic')."
    )
    
    configuration = models.JSONField(
        default=dict,
        help_text="For system models: the JSON schema. For user models: the encrypted config values."
    )
    
    capabilities = models.JSONField(
        default=list, 
        help_text="List of capabilities (e.g., ['text', 'vision', 'tool_use'])."
    )
    
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_system_model', 'provider', 'name']
        constraints = [
            models.UniqueConstraint(fields=['owner_id', 'name'], name='unique_user_model_name')
        ]
        verbose_name = "AI Model Configuration" 

    def __str__(self):
        model_type = 'System' if self.is_system_model else f"User ({self.owner_id})"
        return f"{self.name} [{self.provider}] ({model_type})"