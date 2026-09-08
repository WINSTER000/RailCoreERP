"""User and Role models for RailCore ERP."""

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class Role(models.Model):
    """A job function inside the railway organisation."""

    ADMIN = "Admin"
    RAILWAY_MANAGER = "Railway Manager"
    STATION_MANAGER = "Station Manager"
    OPERATIONS_STAFF = "Operations Staff"

    NAME_CHOICES = [
        (ADMIN, "Admin"),
        (RAILWAY_MANAGER, "Railway Manager"),
        (STATION_MANAGER, "Station Manager"),
        (OPERATIONS_STAFF, "Operations Staff"),
    ]

    #: (name, description) pairs used by the ``seed_data`` command.
    DEFAULT_ROLES = [
        (ADMIN, "Unrestricted access to every RailCore ERP module and setting."),
        (
            RAILWAY_MANAGER,
            "Owns rolling stock and the network plan: trains, routes and schedules.",
        ),
        (
            STATION_MANAGER,
            "Owns station infrastructure: stations, platforms and route stations.",
        ),
        (
            OPERATIONS_STAFF,
            "Runs day to day operations: schedules, delays and cancellations.",
        ),
    ]

    name = models.CharField(max_length=50, unique=True, choices=NAME_CHOICES)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self):
        return self.name

    @property
    def user_count(self):
        return self.users.filter(is_deleted=False).count()


class ActiveUserManager(DjangoUserManager):
    """Manager that hides soft deleted accounts."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class User(AbstractUser):
    """Custom user with a role, contact details and soft deletion."""

    phone_validator = RegexValidator(
        regex=r"^[0-9+\-\s()]{7,20}$",
        message="Enter a valid phone number (7-20 digits, spaces, +, - or brackets).",
    )

    email = models.EmailField("email address")
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        help_text="Determines which RailCore modules this user may open.",
    )
    phone = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    profile_image = models.ImageField(upload_to="profiles/", blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    #: Every account, including soft deleted ones (required by ``createsuperuser``
    #: and by the Django authentication backend).
    objects = DjangoUserManager()
    #: Only accounts that have not been soft deleted.
    active_objects = ActiveUserManager()

    class Meta(AbstractUser.Meta):
        ordering = ["first_name", "last_name", "username"]

    def __str__(self):
        return self.display_name

    # -- naming helpers ---------------------------------------------------
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_name(self):
        return self.full_name or self.username

    @property
    def initials(self):
        if self.first_name or self.last_name:
            first = self.first_name[:1]
            last = self.last_name[:1]
            return (first + last).upper() or self.username[:2].upper()
        return self.username[:2].upper()

    # -- role helpers ----------------------------------------------------
    @property
    def role_name(self):
        if self.role_id and self.role:
            return self.role.name
        return "Administrator" if self.is_superuser else "No role assigned"

    @property
    def is_admin(self):
        return self.is_superuser or (self.role_id is not None and self.role.name == Role.ADMIN)

    @property
    def is_railway_manager(self):
        return self.role_id is not None and self.role.name == Role.RAILWAY_MANAGER

    @property
    def is_station_manager(self):
        return self.role_id is not None and self.role.name == Role.STATION_MANAGER

    @property
    def is_operations_staff(self):
        return self.role_id is not None and self.role.name == Role.OPERATIONS_STAFF

    # -- soft deletion ---------------------------------------------------
    def soft_delete(self):
        """Deactivate the account without destroying its history."""
        self.is_deleted = True
        self.is_active = False
        self.save(update_fields=["is_deleted", "is_active", "updated_at"])

    def restore(self):
        self.is_deleted = False
        self.is_active = True
        self.save(update_fields=["is_deleted", "is_active", "updated_at"])

    @property
    def member_since(self):
        return self.created_at or self.date_joined or timezone.now()
