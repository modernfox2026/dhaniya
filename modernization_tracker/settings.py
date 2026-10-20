import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'change-me-before-production')
DEBUG = os.getenv('DJANGO_DEBUG', 'false').lower() == 'true'
ALLOWED_HOSTS = ['localhost', '172.22.128.1']

INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'tracker',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'modernization_tracker.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'modernization_tracker.wsgi.application'

use_windows_auth = os.getenv("DB_USE_WINDOWS_AUTH", "false").lower() == "true"

database_options = {
    "driver": os.getenv(
        "DB_DRIVER",
        "ODBC Driver 18 for SQL Server"
    ),
    "extra_params": (
        f"Encrypt={os.getenv('DB_ENCRYPT', 'no')};"
        f"TrustServerCertificate="
        f"{os.getenv('DB_TRUST_SERVER_CERTIFICATE', 'yes')}"
    ),
}

if use_windows_auth:
    database_options["trusted_connection"] = "yes"

DATABASES = {
    "default": {
        "ENGINE": "mssql",
        "NAME": os.getenv(
            "DB_NAME",
            "FoxProModernizationTracker"
        ),
        "HOST": os.getenv(
            "DB_HOST",
            r"(localdb)\MSSQLLocalDB"
        ),
        "PORT": os.getenv("DB_PORT", ""),
        "USER": "" if use_windows_auth else os.getenv("DB_USER", ""),
        "PASSWORD": "" if use_windows_auth else os.getenv("DB_PASSWORD", ""),
        "OPTIONS": database_options,
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}
AUTH_PASSWORD_VALIDATORS = [

    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},

]
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'board'
LOGOUT_REDIRECT_URL = 'login'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
