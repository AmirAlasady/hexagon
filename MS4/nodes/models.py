# in nodes/models.py

import uuid
from django.db import models

class Node(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    project_id = models.UUIDField(
        db_index=True,
        help_text="The Project this Node belongs to."
    )
    
    # ------------------ THE ONE AND ONLY FIX IS HERE ------------------
    owner_id = models.UUIDField(
        db_index=True,
        help_text="The UUID of the user who owns this Node. Corresponds to the User UUID in the Auth service JWT."
    )
    # --------------------------------------------------------------------
    
    name = models.CharField(
        max_length=255,
        help_text="The user-defined name for this Node (e.g., 'My Research Agent')."
    )

    configuration = models.JSONField(
        default=dict,
        help_text="The complete configuration blueprint for this node's behavior."
    )

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Node"
        verbose_name_plural = "Nodes"

    def __str__(self):
        return f"{self.name} (Project: {self.project_id})"