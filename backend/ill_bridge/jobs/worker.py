# Create an application bootstrap module for solving circular import issues with Procrastinate.
# ERROR:procrastinate.worker.worker:Task was not found:
from ill_bridge.jobs.app import app
from ill_bridge.jobs import tasks  # registers tasks
