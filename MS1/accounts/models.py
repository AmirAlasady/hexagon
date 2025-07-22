import uuid  # Import the uuid module
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

# Your UserManager remains the same, it doesn't care about the PK type.
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Super user must have is_staff = True")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Super user must have is_superuser = True")

        return self.create_user(email, password, **extra_fields)

# We add PermissionsMixin for standard Django permission handling, which is good practice.
class User(AbstractBaseUser, PermissionsMixin):
    # --- THE KEY CHANGE IS HERE ---
    # We define 'id' as our primary key.
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the user, used across all services."
    )
    
    email = models.EmailField(unique=True, max_length=255)
    username = models.CharField(max_length=50, unique=True)

    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    
    is_superuser = models.BooleanField(default=False)
    
    date_joined = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = UserManager()

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return self.email