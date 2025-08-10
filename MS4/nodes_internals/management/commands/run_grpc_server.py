import grpc
from concurrent import futures
import time
from django.core.management.base import BaseCommand
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MS4.settings')
django.setup()

from nodes_internals.generated import node_pb2_grpc
from nodes_internals.servicer import NodeServicer

class Command(BaseCommand):
    help = 'Starts the gRPC server for the Node Service'
    def handle(self, *args, **options):
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        node_pb2_grpc.add_NodeServiceServicer_to_server(NodeServicer(), server)
        server.add_insecure_port('[::]:50051')
        server.start()
        self.stdout.write(self.style.SUCCESS('Node Service gRPC server started on port 50051.'))
        try:
            while True:
                time.sleep(86400)
        except KeyboardInterrupt:
            server.stop(0)