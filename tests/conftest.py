from __future__ import annotations

# Set SECRET_KEY before any app module is imported so the production guard in
# create_app() does not fire during the test suite (debug=False is the default,
# and the default secret is "dev-secret-change-me").
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-suite")
