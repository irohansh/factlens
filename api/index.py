import sys
from pathlib import Path

# Add project root to sys.path so 'factlens' is discoverable in Vercel serverless functions
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from factlens.api import app

# Vercel entrypoint
# app is the FastAPI ASGI application instance
