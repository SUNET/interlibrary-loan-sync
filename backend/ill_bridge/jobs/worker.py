# Create an application bootstrap module for solving circular import issues with Procrastinate.
# ERROR:procrastinate.worker.worker:Task was not found:
from ill_bridge.jobs.app import create_procrastinate_app
from ill_bridge.jobs import tasks  # registers tasks

app = create_procrastinate_app()
