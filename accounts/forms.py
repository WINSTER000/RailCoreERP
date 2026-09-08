"""Forms for sign in, self-service profile editing and user administration."""

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from .models import Role, User

#: Fields an employee may change about their own account.
PROFILE_FIELDS = ("first_name", "last_name", "email", "phone", "profile_image")

#: Everything an administrator may set on somebody else's account.
ACCOUNT_FIELDS = (
    "username",
    "first_name",
    "last_name",
    "email",
    "role",
    "phone",
    "profile_image",
    "is_active",
)

#: Browser hints added on top of the RailCore widget classes, keyed by field name.
FIELD_ATTRS = {
    "username": {"placeholder": "e.g. r.sharma", "autocomplete": "username"},
    "first_name": {"placeholder": "e.g. Rahul", "autocomplete": "given-name"},
    "last_name": {"placeholder": "e.g. Sharma", "autocomplete": "family-name"},
    "email": {"placeholder": "name@railcore.in", "autocomplete": "email"},
    "phone": {"placeholder": "e.g. +91 98765 43210", "autocomplete": "tel"},
}

#: Shared field labels so the three account forms read the same way.
ACCOUNT_LABELS = {
    "profile_image": "Profile photo",
    "is_active": "Account is active",
}


def _decorate_widgets(form):
    """Give every widget its RailCore CSS class plus useful browser hints.

    ``templates/partials/_field.html`` renders the widget as-is, so the classes
    from SPEC section 7.2 have to be attached here.
    """
    for name, field in form.fields.items():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            # Rendered inside the .rc-switch label, which styles the input itself.
            continue
        if isinstance(widget, forms.Select):
            widget.attrs.setdefault("class", "rc-select")
        elif isinstance(widget, forms.ClearableFileInput):
            widget.attrs.setdefault("class", "rc-file")
            widget.attrs.setdefault("accept", "image/*")
        elif isinstance(widget, forms.Textarea):
            widget.attrs.setdefault("class", "rc-textarea")
        else:
            widget.attrs.setdefault("class", "rc-input")
        widget.attrs.update(FIELD_ATTRS.get(name, {}))


def _limit_role_choices(form):
    """Offer only the roles that are currently in use."""
    role_field = form.fields.get("role")
    if role_field is not None:
        role_field.queryset = Role.objects.filter(is_active=True)
        role_field.empty_label = "No role assigned"


def _unique_email(email, instance=None):
    """Reject an address already held by another account that is still live."""
    email = (email or "").strip()
    if not email:
        return email
    taken = User.active_objects.filter(email__iexact=email)
    if instance is not None and instance.pk:
        taken = taken.exclude(pk=instance.pk)
    if taken.exists():
        raise forms.ValidationError("Another account already uses this email address.")
    return email


class LoginForm(AuthenticationForm):
    """Username and password sign in form used by ``accounts/login.html``."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Incorrect username or password. Please try again.",
        "inactive": "This account has been deactivated. Contact a RailCore administrator.",
        "deleted": "This account has been deleted. Contact a RailCore administrator.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "class": "rc-input",
                "placeholder": "Your RailCore username",
                "autocomplete": "username",
                "autofocus": True,
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": "rc-input",
                "placeholder": "Your password",
                "autocomplete": "current-password",
            }
        )

    def confirm_login_allowed(self, user):
        """Block soft deleted accounts before a session is created."""
        if user.is_deleted:
            raise forms.ValidationError(self.error_messages["deleted"], code="deleted")
        super().confirm_login_allowed(user)


class UserCreateForm(forms.ModelForm):
    """Administrator form that opens an account and sets its first password."""

    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Type the same password again so typing mistakes are caught.",
    )

    field_order = (
        "username",
        "first_name",
        "last_name",
        "email",
        "role",
        "phone",
        "password1",
        "password2",
        "profile_image",
        "is_active",
    )

    class Meta:
        model = User
        fields = ACCOUNT_FIELDS
        labels = ACCOUNT_LABELS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _limit_role_choices(self)
        _decorate_widgets(self)
        self.fields["password1"].help_text = " ".join(
            password_validation.password_validators_help_texts()
        )

    def clean_email(self):
        return _unique_email(self.cleaned_data.get("email"), self.instance)

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("The two passwords do not match.")
        return password2

    def _post_clean(self):
        """Validate the password once the account fields are on the instance.

        Running last lets ``UserAttributeSimilarityValidator`` compare the
        password against the username, name and email that were just entered.
        """
        super()._post_clean()
        password = self.cleaned_data.get("password2")
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except forms.ValidationError as error:
                self.add_error("password2", error)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class UserUpdateForm(forms.ModelForm):
    """Administrator form for editing an existing account, password excluded."""

    class Meta:
        model = User
        fields = ACCOUNT_FIELDS
        labels = ACCOUNT_LABELS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _limit_role_choices(self)
        _decorate_widgets(self)

    def clean_email(self):
        return _unique_email(self.cleaned_data.get("email"), self.instance)


class ProfileForm(forms.ModelForm):
    """What an employee may change about themselves: never role or username."""

    class Meta:
        model = User
        fields = PROFILE_FIELDS
        labels = {"profile_image": "Profile photo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _decorate_widgets(self)

    def clean_email(self):
        return _unique_email(self.cleaned_data.get("email"), self.instance)


class RailCorePasswordChangeForm(PasswordChangeForm):
    """Django's password change form wearing the RailCore input styles."""

    AUTOCOMPLETE = {
        "old_password": "current-password",
        "new_password1": "new-password",
        "new_password2": "new-password",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.update(
                {
                    "class": "rc-input",
                    "autocomplete": self.AUTOCOMPLETE.get(name, "off"),
                }
            )
        self.fields["old_password"].widget.attrs["autofocus"] = True
