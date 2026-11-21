"""Print the API's OpenAPI schema as JSON, without starting a server.

    python -m ptashka.cli.export_openapi > ../frontend/openapi.json

The frontend generates its TypeScript types from it (`npm run gen:api`), so the
backend's Pydantic schemas are the single source of truth for the API contract.
"""

import json

from ptashka.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=2))
