import os


SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

SQLALCHEMY_DATABASE_URI = os.environ[
    "SUPERSET_DATABASE_URI"
]

MAPBOX_API_KEY = os.environ.get(
    "MAPBOX_API_KEY",
    "",
)

SUPERSET_HOME_PATH = "/dashboard/list/"

WTF_CSRF_ENABLED = True
FEATURE_FLAGS = {
    "ENABLE_JAVASCRIPT_CONTROLS": True,
}
from superset.config import TALISMAN_CONFIG

TALISMAN_CONFIG[
    "content_security_policy"
][
    "script-src"
].append("'unsafe-eval'")