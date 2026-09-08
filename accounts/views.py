"""Authentication, self-service profile and user administration views."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from activity_logs.models import ActivityLog
from activity_logs.services import log_create, log_delete, log_update
from notifications.models import Notification
from notifications.services import notify_roles, unread_count
from railway.utils import apply_search, apply_sort, paginate

from .forms import (
    LoginForm,
    ProfileForm,
    RailCorePasswordChangeForm,
    UserCreateForm,
    UserUpdateForm,
)
from .models import Role, User
from .permissions import MODULE_PERMISSIONS, permission_map, require_manage, require_view

#: Columns the user directory may be ordered by (matches the sort headers used
#: in ``templates/accounts/user_list.html``).
USER_SORT_FIELDS = ("username", "first_name", "email", "role__name", "created_at")

#: ``?status=`` choices for the user directory.
USER_STATUS_OPTIONS = [
    ("active", "Active"),
    ("inactive", "Inactive"),
    ("deleted", "Deleted"),
]

#: Fields searched by the ``?q=`` box of the user directory.
USER_SEARCH_FIELDS = ["username", "first_name", "last_name", "email"]


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------
def _plural(count, word):
    """``1 account`` / ``4 accounts`` for the page subtitles."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _capability_rows(account):
    """What the role of *account* may do, as rows for a readable table."""
    rows = []
    for module, capability in permission_map(account).items():
        manageable = bool(MODULE_PERMISSIONS[module]["manage"])
        can_manage = capability["manage"] and manageable
        if can_manage:
            access_label = "View and manage"
        elif capability["view"]:
            access_label = "View only"
        else:
            access_label = "No access"
        rows.append(
            {
                "module": module,
                "label": module.replace("_", " ").title(),
                "can_view": capability["view"],
                "can_manage": can_manage,
                "access_label": access_label,
            }
        )
    return rows


def _recent_activity(account, limit=10):
    """The newest audit entries written by *account*."""
    return list(ActivityLog.objects.select_related("user").filter(user=account)[:limit])


def _safe_redirect_target(request, next_url):
    """Follow ``?next=`` only when it stays on this site, else the default page."""
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return settings.LOGIN_REDIRECT_URL


def _accounts_for_status(status_filter):
    """Directory queryset: soft deleted rows appear only when asked for."""
    if status_filter == "deleted":
        return User.objects.filter(is_deleted=True)
    if status_filter == "active":
        return User.active_objects.filter(is_active=True)
    if status_filter == "inactive":
        return User.active_objects.filter(is_active=False)
    return User.active_objects.all()


def _active_admin_count(exclude_pk=None):
    """How many usable administrator accounts remain."""
    admins = User.active_objects.filter(is_active=True).filter(
        Q(role__name=Role.ADMIN) | Q(is_superuser=True)
    )
    if exclude_pk is not None:
        admins = admins.exclude(pk=exclude_pk)
    return admins.count()


def _account_form_context(form, account=None):
    """Shared context for ``accounts/user_form.html``."""
    editing = account is not None
    return {
        "form": form,
        "account": account,
        "user_obj": account,
        "is_edit": editing,
        "page_title": "Edit User" if editing else "Add User",
        "page_subtitle": (
            f"@{account.username} · {account.role_name}"
            if editing
            else "Open an account and choose the role it works under"
        ),
        "active_nav": "users",
        "form_title": account.display_name if editing else "New employee account",
        "form_description": (
            "Update the account details and the role that grants its access."
            if editing
            else "Create the account, set its first password and assign a role."
        ),
        "cancel_url": (
            reverse("accounts:user_detail", args=[account.pk])
            if editing
            else reverse("accounts:user_list")
        ),
        "submit_label": "Save Changes" if editing else "Create User",
    }


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
@never_cache
@sensitive_post_parameters()
def login_view(request):
    """Sign an employee in and send them on to the dashboard."""
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()

    if request.method == "POST":
        form = LoginForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.display_name}.")
            return redirect(_safe_redirect_target(request, next_url))
        messages.error(request, "Sign in failed. Please check the details below and try again.")
    else:
        form = LoginForm(request=request)

    context = {
        "form": form,
        "next": next_url,
        "page_title": "Sign in",
        "page_subtitle": "Access your RailCore ERP workspace",
        "active_nav": "",
    }
    return render(request, "accounts/login.html", context)


@login_required
def logout_view(request):
    """End the session. Only a POST signs the employee out."""
    if request.method != "POST":
        return redirect("dashboard:home")

    logout(request)
    messages.success(request, "You have been signed out. See you next time.")
    return redirect("accounts:login")


# ---------------------------------------------------------------------------
# My profile
# ---------------------------------------------------------------------------
@require_view("profile")
def profile_view(request):
    """Show and edit the signed in employee's own details."""
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            account = form.save()
            log_update(request.user, account, f"Updated own profile details ({account.username})")
            messages.success(request, "Your profile was updated successfully.")
            return redirect("accounts:profile")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = ProfileForm(instance=request.user)

    account = request.user
    context = {
        "form": form,
        "account": account,
        "user_obj": account,
        "capabilities": _capability_rows(account),
        "recent_activity": _recent_activity(account),
        "unread_count": unread_count(account),
        "password_change_url": reverse("accounts:password_change"),
        "page_title": "My Profile",
        "page_subtitle": f"@{account.username} · {account.role_name}",
        "active_nav": "profile",
    }
    return render(request, "accounts/profile.html", context)


@require_view("profile")
@sensitive_post_parameters()
def password_change_view(request):
    """Let an employee change their own password without being signed out."""
    if request.method == "POST":
        form = RailCorePasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            account = form.save()
            update_session_auth_hash(request, account)
            log_update(request.user, account, "Changed account password")
            messages.success(request, "Your password was changed successfully.")
            return redirect("accounts:profile")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = RailCorePasswordChangeForm(request.user)

    context = {
        "form": form,
        "account": request.user,
        "form_title": "Change password",
        "form_description": "Confirm your current password, then choose a new one.",
        "cancel_url": reverse("accounts:profile"),
        "submit_label": "Update Password",
        "page_title": "Change Password",
        "page_subtitle": "Keep your RailCore account secure",
        "active_nav": "profile",
    }
    return render(request, "accounts/password_change.html", context)


# ---------------------------------------------------------------------------
# User administration
# ---------------------------------------------------------------------------
@require_view("users")
def user_list(request):
    """Searchable, sortable directory of every RailCore employee account."""
    q = (request.GET.get("q") or "").strip()
    role_filter = (request.GET.get("role") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()

    accounts = _accounts_for_status(status_filter).select_related("role")
    accounts = apply_search(accounts, q, USER_SEARCH_FIELDS)
    if role_filter:
        accounts = accounts.filter(role__name=role_filter)
    accounts = apply_sort(accounts, request.GET.get("sort"), USER_SORT_FIELDS, "username")

    page_obj = paginate(request, accounts)
    role_options = [(role.name, role.name) for role in Role.objects.filter(is_active=True)]
    total_count = page_obj.paginator.count

    context = {
        "users": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "role_filter": role_filter,
        "status_filter": status_filter,
        "role_options": role_options,
        "status_options": USER_STATUS_OPTIONS,
        "total_count": total_count,
        "add_url": reverse("accounts:user_add"),
        "page_title": "Users",
        "page_subtitle": (
            f"{_plural(total_count, 'account')} across {_plural(len(role_options), 'active role')}"
        ),
        "active_nav": "users",
    }
    return render(request, "accounts/user_list.html", context)


@require_manage("users")
@sensitive_post_parameters()
def user_create(request):
    """Open a new employee account and tell the administrators about it."""
    if request.method == "POST":
        form = UserCreateForm(request.POST, request.FILES)
        if form.is_valid():
            account = form.save()
            log_create(
                request.user,
                account,
                f"Added user {account.username} - {account.role_name}",
            )
            notify_roles(
                [Role.ADMIN],
                "New user account created",
                f"{account.display_name} was added to RailCore ERP as {account.role_name}.",
                level=Notification.INFO,
                url=reverse("accounts:user_detail", args=[account.pk]),
                exclude=request.user,
            )
            messages.success(request, f"User {account.username} was added successfully.")
            return redirect("accounts:user_detail", pk=account.pk)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = UserCreateForm()

    return render(request, "accounts/user_form.html", _account_form_context(form))


@require_view("users")
def user_detail(request, pk):
    """Everything an administrator needs to know about one account."""
    account = get_object_or_404(User.objects.select_related("role"), pk=pk)
    notifications = Notification.objects.filter(user=account)

    context = {
        "account": account,
        "user_obj": account,
        "capabilities": _capability_rows(account),
        "recent_activity": _recent_activity(account),
        "notification_count": notifications.count(),
        "unread_count": notifications.filter(is_read=False).count(),
        "page_title": account.display_name,
        "page_subtitle": f"@{account.username} · {account.role_name}",
        "active_nav": "users",
    }
    return render(request, "accounts/user_detail.html", context)


@require_manage("users")
def user_update(request, pk):
    """Edit an existing account: details, role and active flag."""
    account = get_object_or_404(User.objects.select_related("role"), pk=pk)

    if request.method == "POST":
        form = UserUpdateForm(request.POST, request.FILES, instance=account)
        if form.is_valid():
            account = form.save()
            log_update(request.user, account, f"Updated user {account.username}")
            messages.success(request, f"User {account.username} was updated successfully.")
            return redirect("accounts:user_detail", pk=account.pk)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = UserUpdateForm(instance=account)

    return render(request, "accounts/user_form.html", _account_form_context(form, account))


@require_manage("users")
def user_delete(request, pk):
    """Soft delete an account, keeping its audit trail intact."""
    account = get_object_or_404(User.objects.select_related("role"), pk=pk)

    if account.pk == request.user.pk:
        messages.error(request, "You cannot delete the account you are signed in with.")
        return redirect("accounts:user_list")

    if account.is_admin and _active_admin_count(exclude_pk=account.pk) == 0:
        messages.error(
            request,
            f"User {account.username} is the last active administrator and cannot be deleted.",
        )
        return redirect("accounts:user_list")

    log_count = ActivityLog.objects.filter(user=account).count()

    if request.method == "POST":
        account.soft_delete()
        log_delete(request.user, account, f"Deleted user {account.username}")
        messages.success(request, f"User {account.username} was deleted successfully.")
        return redirect("accounts:user_list")

    entries = "entry" if log_count == 1 else "entries"
    context = {
        "page_title": "Delete User",
        "page_subtitle": f"@{account.username} · {account.role_name}",
        "active_nav": "users",
        "object_type": "User",
        "object_label": f"{account.display_name} (@{account.username})",
        "object_meta": [
            ("Role", account.role_name),
            ("Email", account.email or "Not provided"),
            ("Status", "Active" if account.is_active else "Inactive"),
            ("Activity entries", log_count),
        ],
        "warning": (
            f"{log_count} activity log {entries} recorded for this account "
            "will be kept for auditing."
            if log_count
            else ""
        ),
        "soft_delete": True,
        "cancel_url": reverse("accounts:user_detail", args=[account.pk]),
        "confirm_label": "Yes, delete user",
    }
    return render(request, "partials/_confirm_delete.html", context)


@require_manage("users")
@require_POST
def user_restore(request, pk):
    """Bring a soft deleted account back into service."""
    account = get_object_or_404(User.objects.select_related("role"), pk=pk)
    if account.is_deleted:
        account.restore()
        log_update(request.user, account, f"Restored user {account.username}")
        messages.success(request, f"User {account.username} was restored successfully.")
    else:
        messages.info(request, f"User {account.username} is already active.")
    return redirect("accounts:user_detail", pk=account.pk)
