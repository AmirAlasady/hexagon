# in nodes/repository.py

from typing import List, Optional
import uuid
from .models import Node

class NodeRepository:
    def find_by_id(self, node_id: uuid.UUID) -> Optional[Node]:
        try:
            return Node.objects.get(id=node_id)
        except Node.DoesNotExist:
            return None

    def find_by_project(self, project_id: uuid.UUID) -> List[Node]:
        return list(Node.objects.filter(project_id=project_id))

    def create(self, *, project_id: uuid.UUID, owner_id: int, name: str, configuration: dict) -> Node:
        return Node.objects.create(
            project_id=project_id,
            owner_id=owner_id,
            name=name,
            configuration=configuration
        )

    def update(self, node: Node, name: str, configuration: dict) -> Node:
        node.name = name
        node.configuration = configuration
        node.save(update_fields=['name', 'configuration', 'updated_at'])
        return node

    def delete(self, node: Node) -> None:
        node.delete()