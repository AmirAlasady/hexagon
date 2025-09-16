import grpc, time, logging, os, django
from concurrent import futures
from django.core.management.base import BaseCommand

logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS10-gRPC - %(levelname)s - %(message)s')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MS10.settings')
django.setup()

from data_internals import data_pb2_grpc
from data_internals.servicer import DataServicer

class Command(BaseCommand):
    help = 'Starts the gRPC server for the Data Service'
    def handle(self, *args, **options):
        port = '50058'
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        data_pb2_grpc.add_DataServiceServicer_to_server(DataServicer(), server)
        server.add_insecure_port(f'[::]:{port}')
        server.start()
        self.stdout.write(self.style.SUCCESS(f'Data Service gRPC server started on port {port}.'))
        server.wait_for_termination()