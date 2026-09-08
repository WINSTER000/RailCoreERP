from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Accounts & Roles"

    def ready(self):
        # Registers the login/logout activity-log receivers.
        from . import signals  # noqa: F401
