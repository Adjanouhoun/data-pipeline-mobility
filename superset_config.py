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