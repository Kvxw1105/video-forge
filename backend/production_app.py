"""Production-style local entrypoint serving the built VideoForge frontend."""

from main import create_app

app = create_app(serve_frontend=True)
