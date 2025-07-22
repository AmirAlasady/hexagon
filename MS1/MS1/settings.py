
from datetime import timedelta
import os
from pathlib import Path



# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    # This fallback should ideally not be hit if .env is loaded correctly
    # or if the environment variable is set directly in the deployment environment.
    SECRET_KEY = 'django-insecure-fallback-dev-key-!!change-me!!'
    print("WARNING: DJANGO_SECRET_KEY not found in environment or .env. Using fallback. THIS IS INSECURE FOR PRODUCTION.")

DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in ('true', '1', 't')

# SECURITY WARNING: don't run with debug turned on in production!
#DEBUG = True

ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'djoser',
    'rest_framework_simplejwt.token_blacklist',
    'rest_framework.authtoken',
    'accounts.apps.AccountsConfig',

]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'MS1.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'MS1.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Authentication
AUTH_USER_MODEL = "accounts.User"
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
# These are the general rules for all API interactions.
REST_FRAMEWORK = {

    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    
    """
    By default, 
    every time someone shows me an access card, 
    I will use my JWT scanner (JWTAuthentication) to check if it's valid.
    """
     #
     #
   #####
    ###
     #
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),


    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',  # Adjust as needed for unauthenticated requests
        'user': '20000/day' # Adjust as needed for authenticated requests
    }
}


# This is the detailed configuration for the "access card" (JWT) itself.
SIMPLE_JWT = {

    """
    TOKEN_OBTAIN_SERIALIZER: 
    "When I create a new access card, 
    I won't just use the standard template. 
    I'll use my own custom template (CustomTokenObtainPairSerializer)
    to add extra information to it."
    """
     #
     #
   #####
    ###
     #
    "TOKEN_OBTAIN_SERIALIZER": "accounts.serializers.CustomTokenObtainPairSerializer",
    
    "SIGNING_KEY": JWT_SECRET_KEY,  # <<< USE DJANGO'S SECRET_KEY LOADED FROM ENV
    "VERIFYING_KEY": JWT_SECRET_KEY,
    "ISSUER": os.getenv('JWT_ISSUER', "https://ms1.auth-service.com"), # Define your issuer
    
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60), # e.g., 1 hour
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),    # e.g., 1 day
    "ROTATE_REFRESH_TOKENS": False, # Set to True if you want new refresh token on each refresh
    "BLACKLIST_AFTER_ROTATION": False, # Requires setting up blacklist app if ROTATE_REFRESH_TOKENS is True
    "UPDATE_LAST_LOGIN": True, # Updates user's last_login field upon successful token generation

    "ALGORITHM": "HS256",
    
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",

    "JTI_CLAIM": "jti",

}

DJOSER = {
    'LOGIN_FIELD': 'email',                         # Use email for login
    'SEND_ACTIVATION_EMAIL': False,                 # Disable activation email
    'SEND_CONFIRMATION_EMAIL': False,               # Disable confirmation email on registration
    'USER_ID_FIELD': 'id',
    'USER_CREATE_PASSWORD_RETYPE': True,          # Require password retype on registration
    'SET_PASSWORD_RETYPE': True,                  # Require password retype for /users/set_password/
    'PASSWORD_RESET_CONFIRM_RETYPE': True,        # Require password retype for /users/reset_password_confirm/
    # 'USERNAME_RESET_CONFIRM_RETYPE': True,      # For the separate 'username' field if you enable username reset via Djoser
    # 'ACTIVATION_URL': 'activate/{uid}/{token}', # Not needed
    'PASSWORD_RESET_CONFIRM_URL': 'password/reset/confirm/{uid}/{token}', # For frontend routing
    # 'USERNAME_RESET_CONFIRM_URL': 'username/reset/confirm/{uid}/{token}', # For frontend routing

    'SERIALIZERS': {
        'user_create': 'accounts.serializers.UserCreateSerializer',
        'user': 'accounts.serializers.UserSerializer',
        
    },
    'USERNAME_RESET_CONFIRM_URL': 'username/reset/confirm/{uid}/{token}',
    'PERMISSIONS': {
        # Allow anyone to create a user or request password reset
        'user_create': ['rest_framework.permissions.AllowAny'],
        'password_reset': ['rest_framework.permissions.AllowAny'],
        'password_reset_confirm': ['rest_framework.permissions.AllowAny'],
        # 'username_reset': ['rest_framework.permissions.AllowAny'], # If using Djoser's username reset
        # 'username_reset_confirm': ['rest_framework.permissions.AllowAny'], # If using Djoser's username reset
        # Djoser's JWT endpoints are handled by djoser.urls.jwt, AllowAny is usually fine
        'token_create': ['rest_framework.permissions.AllowAny'],
        'token_destroy': ['rest_framework.permissions.IsAuthenticated'], # Logout
        # Other actions typically require authentication
        'user_delete': ['djoser.permissions.CurrentUserOrAdmin'],
        'user': ['djoser.permissions.CurrentUserOrAdmin'], # for /users/me/
        'set_password': ['djoser.permissions.CurrentUserOrAdmin'],
        'set_username': ['djoser.permissions.CurrentUserOrAdmin'], # For Djoser's /users/set_username/
    },
    # 'USERNAME_CHANGED_EMAIL_CONFIRMATION': True, # If you want email sent when username changes via Djoser
    # 'PASSWORD_CHANGED_EMAIL_CONFIRMATION': True, # If you want email sent when password changes via Djoser

    # HIDE_USERS needs to be False for /users/me/ to work without being admin
    'HIDE_USERS': False,
}

# For development, to see password reset emails in the console
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'