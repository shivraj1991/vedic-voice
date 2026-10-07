"""AWS Lambda entry point (API Gateway HTTP API -> Mangum -> FastAPI).

The app is built once per container (cold start) and reused across requests.
"""

from mangum import Mangum

from .api.app import create_app

handler = Mangum(create_app(), lifespan="off")
