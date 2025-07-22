
from datetime import timedelta
import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    # This fallback should ideally not be hit if .env is loaded correctly
    # or if the environment variable is set directly in the deployment environment.
    SECRET_KEY = 'django-insecure-fallback-dev-key-!!change-me!!'
    print("WARNING: DJANGO_SECRET_KEY not found in environment or .env. Using fallback. THIS IS INSECURE FOR PRODUCTION.")

DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in ('true', '1', 't')

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
    'project'
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

ROOT_URLCONF = 'MS2.urls'

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

WSGI_APPLICATION = 'MS2.wsgi.application'


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


JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')



REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # "rest_framework_simplejwt.authentication.JWTAuthentication", # Comment out or remove default
        """
        Deconstructing the Code: Key Components Explained
        1. The custom_auth.py and ForceTokenUserJWTAuthentication
        This file is the most important piece of logic in this entire service. It's the "park ranger at the gate."
        What is JWTAuthentication? The default class from simple-jwt tries to do two things: 1) validate the token, and 2) use the user ID from the token to look up a User object in the local database.
        Why is that a problem? Your Project Service (MS2) has no User table! If it tried to do a local lookup, it would fail every time.
        What does your ForceTokenUserJWTAuthentication do? You have cleverly subclassed it and overridden the get_user method. Your version does this:
        It still lets the parent class do the hard work of validating the token's signature and expiration.
        Once the token is proven valid, your get_user method steps in.
        Instead of looking in the database, it says, "Just create a lightweight, temporary user object in memory called a TokenUser. Take the user ID directly from the token and stick it on this temporary object."
        This TokenUser object is then attached to the request as request.user.
        The result: request.user is now a simple object where request.user.id contains the UUID from the JWT, allowing the rest of your application (views, permissions) to work as if there were a real user, without ever touching a local user database. This is a beautiful and correct implementation.

        """
     #
     #
   #####
    ###
     #        
        "project.custom_auth.ForceTokenUserJWTAuthentication", # <<< YOUR CUSTOM AUTH CLASS
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


SIMPLE_JWT = {

    "SIGNING_KEY": JWT_SECRET_KEY,  # <<< USE DJANGO'S SECRET_KEY LOADED FROM ENV
    "VERIFYING_KEY": JWT_SECRET_KEY,
    "ISSUER": os.getenv('JWT_ISSUER', "https://ms1.auth-service.com"), # MUST match MS1's issuer
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60), # e.g., 1 hour
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),    # e.g., 1 day
    "LEEWAY": timedelta(seconds=10),
    "ALGORITHM": "HS256",
    
    # --- Settings related to interpreting the token payload ---
    """
"USER_ID_CLAIM": "user_id": (Your Specific Question)
 This is a critical instruction. It tells simple-jwt:
   "When you parse the token's payload (the data inside),
     the claim that contains the user's primary identifier is named 'user_id'."
       Your MS1's CustomTokenObtainPairSerializer probably adds a claim with this name.
    """

    "USER_ID_CLAIM": "user_id",

    "USER_ID_FIELD": "id",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser", # Explicitly use TokenUse

    # --- Settings for features MS2 likely DOES NOT use ---
    "UPDATE_LAST_LOGIN": False,
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False, 

}
