"""Test environment. Set before any module under test is imported: a throwaway
SQLite file (one shared file, because an in-memory SQLite is a different
database per connection), no scheduler, and a test admin address so admin
paths are exercised without anyone's real email."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DB = os.path.join(tempfile.gettempdir(), "job_hunter_test_api.db")
for _p in (_DB, _DB + "-journal"):
    try:
        os.remove(_p)
    except OSError:
        pass
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + _DB.replace("\\", "/")
os.environ["DISABLE_SCHEDULER"] = "1"
os.environ["ADMIN_EMAIL"] = "admin@test.local"
os.environ.setdefault("SECRET_KEY", "test-secret-key")
