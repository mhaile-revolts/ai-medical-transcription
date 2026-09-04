"""Project-wide pytest configuration."""

import os

# Tests use synthetic data and intentionally exercise the explicit ephemeral
# adapters unless an isolated subprocess overrides this for durable integration.
os.environ.setdefault("APP_MODE", "demo")