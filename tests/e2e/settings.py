import os

DEBUG = True
ALLOWED_HOSTS = ["*"]
SECRET_KEY = "test-secret-key-for-testing-only"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "wagtail",
    "wagtail.admin",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "taggit",
    "wagtail_block_reference",
    "tests.e2e.testapp",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("E2E_DB_PATH", ":memory:"),
    }
}

ROOT_URLCONF = "tests.e2e.urls"

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

SESSION_ENGINE = "django.contrib.sessions.backends.db"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

USE_TZ = True
STATIC_URL = "/static/"
WAGTAIL_SITE_NAME = "Test Site"
WAGTAILADMIN_STATIC_FILE_VERSION_STRINGS = False
