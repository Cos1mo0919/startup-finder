"""Admin key for isolated tests only.

A fresh random value is generated for every test run (or taken from
TEST_ADMIN_KEY, which the Playwright config sets so the browser server and the
specs agree). It never matches a real deployment key.
"""

import os
import secrets

ADMIN_KEY = os.environ.get("TEST_ADMIN_KEY") or secrets.token_urlsafe(24)
os.environ["TEST_ADMIN_KEY"] = ADMIN_KEY
