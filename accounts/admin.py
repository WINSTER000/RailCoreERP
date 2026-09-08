from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Role, User


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "is_active", "user_count", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "full_name",
        "email",
        "role",
        "phone",
        "is_active",
        "is_deleted",
        "created_at",
    )
    list_filter = ("role", "is_active", "is_deleted", "is_staff", "is_superuser")
    search_fields = ("username", "first_name", "last_name", "email", "phone")
    ordering = ("username",)
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "RailCore profile",
            {"fields": ("role", "phone", "profile_image", "is_deleted", "created_at", "updated_at")},
        ),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("RailCore profile", {"fields": ("first_name", "last_name", "email", "role", "phone")}),
    )

    @admin.display(description="Name", ordering="first_name")
    def full_name(self, obj):
        return obj.display_name
