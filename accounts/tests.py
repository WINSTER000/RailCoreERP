"""Authentication, self-service profile and user administration tests."""

from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.urls import reverse

from activity_logs.models import ActivityLog
from notifications.models import Notification

from .factories import PASSWORD, RailCoreTestCase, create_user
from .forms import LoginForm, ProfileForm, UserCreateForm, UserUpdateForm
from .models import Role, User
from .views import _active_admin_count


def _messages(response):
    """Every flash message attached to the request that produced *response*."""
    return [str(message) for message in get_messages(response.wsgi_request)]


class RoleModelTests(RailCoreTestCase):
    def test_string_is_the_role_name(self):
        self.assertEqual(str(self.admin.role), Role.ADMIN)

    def test_the_four_default_roles_are_described(self):
        names = [name for name, _ in Role.DEFAULT_ROLES]
        self.assertEqual(
            names,
            [Role.ADMIN, Role.RAILWAY_MANAGER, Role.STATION_MANAGER, Role.OPERATIONS_STAFF],
        )
        for _, description in Role.DEFAULT_ROLES:
            self.assertTrue(description)

    def test_user_count_ignores_deleted_accounts(self):
        role = self.operations_staff.role
        self.assertEqual(role.user_count, 1)

        self.operations_staff.soft_delete()
        role.refresh_from_db()
        self.assertEqual(role.user_count, 0)


class UserModelTests(RailCoreTestCase):
    def test_display_name_prefers_the_full_name(self):
        account = create_user("d.mehta", first_name="Divya", last_name="Mehta")
        self.assertEqual(account.display_name, "Divya Mehta")
        self.assertEqual(str(account), "Divya Mehta")

    def test_display_name_falls_back_to_the_username(self):
        account = create_user("nameless", first_name="", last_name="")
        self.assertEqual(account.display_name, "nameless")

    def test_initials_use_the_name_then_the_username(self):
        named = create_user("d.mehta", first_name="Divya", last_name="Mehta")
        self.assertEqual(named.initials, "DM")

        nameless = create_user("zephyr", first_name="", last_name="")
        self.assertEqual(nameless.initials, "ZE")

    def test_role_name_reports_the_assigned_role(self):
        self.assertEqual(self.station_manager.role_name, Role.STATION_MANAGER)

    def test_role_name_of_an_account_without_a_role(self):
        orphan = create_user("no_role")
        self.assertEqual(orphan.role_name, "No role assigned")

    def test_a_superuser_without_a_role_reads_as_administrator(self):
        root = create_user("root", is_superuser=True, is_staff=True)
        self.assertEqual(root.role_name, "Administrator")
        self.assertTrue(root.is_admin)

    def test_role_predicates(self):
        self.assertTrue(self.admin.is_admin)
        self.assertTrue(self.railway_manager.is_railway_manager)
        self.assertTrue(self.station_manager.is_station_manager)
        self.assertTrue(self.operations_staff.is_operations_staff)
        self.assertFalse(self.operations_staff.is_admin)

    def test_soft_delete_deactivates_and_hides_the_account(self):
        account = create_user("leaver")
        account.soft_delete()

        self.assertTrue(account.is_deleted)
        self.assertFalse(account.is_active)
        self.assertFalse(User.active_objects.filter(pk=account.pk).exists())
        self.assertTrue(User.objects.filter(pk=account.pk).exists())

    def test_restore_reverses_a_soft_delete(self):
        account = create_user("returner")
        account.soft_delete()
        account.restore()

        self.assertFalse(account.is_deleted)
        self.assertTrue(account.is_active)
        self.assertTrue(User.active_objects.filter(pk=account.pk).exists())

    def test_member_since_is_the_creation_stamp(self):
        self.assertEqual(self.admin.member_since, self.admin.created_at)


class LoginViewTests(RailCoreTestCase):
    def setUp(self):
        self.login_url = reverse("accounts:login")

    def test_the_sign_in_page_is_public(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)

    def test_valid_credentials_start_a_session(self):
        response = self.client.post(
            self.login_url,
            {"username": self.admin.username, "password": PASSWORD},
        )
        self.assertRedirects(response, reverse("dashboard:home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.admin.pk)

    def test_signing_in_records_a_login_entry(self):
        self.client.post(
            self.login_url,
            {"username": self.admin.username, "password": PASSWORD},
        )
        self.assertTrue(
            ActivityLog.objects.filter(
                user=self.admin, action=ActivityLog.LOGIN
            ).exists()
        )

    def test_wrong_password_redisplays_the_form(self):
        response = self.client.post(
            self.login_url,
            {"username": self.admin.username, "password": "not-the-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_failed_sign_in_is_not_logged_as_a_login(self):
        self.client.post(
            self.login_url, {"username": self.admin.username, "password": "wrong"}
        )
        self.assertEqual(ActivityLog.objects.filter(action=ActivityLog.LOGIN).count(), 0)

    def test_a_soft_deleted_account_cannot_sign_in(self):
        account = create_user("removed_staff")
        account.soft_delete()

        response = self.client.post(
            self.login_url, {"username": account.username, "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_login_form_refuses_a_deleted_account(self):
        # Defensive guard: the default ModelBackend already refuses the account
        # because ``soft_delete`` clears ``is_active``.
        account = create_user("ghost_staff")
        account.is_deleted = True

        with self.assertRaises(ValidationError) as caught:
            LoginForm().confirm_login_allowed(account)
        self.assertEqual(caught.exception.code, "deleted")

    def test_an_already_signed_in_employee_is_sent_to_the_dashboard(self):
        self.login(self.operations_staff)
        response = self.client.get(self.login_url)
        self.assertRedirects(response, reverse("dashboard:home"))

    def test_a_safe_next_url_is_followed(self):
        target = reverse("railway:station_list")
        response = self.client.post(
            self.login_url,
            {"username": self.admin.username, "password": PASSWORD, "next": target},
        )
        self.assertRedirects(response, target)

    def test_an_offsite_next_url_is_ignored(self):
        response = self.client.post(
            self.login_url,
            {
                "username": self.admin.username,
                "password": PASSWORD,
                "next": "https://phishing.example.com/steal",
            },
        )
        self.assertRedirects(response, reverse("dashboard:home"))

    def test_the_next_url_survives_the_rendered_form(self):
        target = reverse("railway:train_list")
        response = self.client.get(self.login_url, {"next": target})
        self.assertEqual(response.context["next"], target)

    def test_protected_pages_redirect_anonymous_visitors_to_sign_in(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.login_url, response["Location"])


class LogoutViewTests(RailCoreTestCase):
    def setUp(self):
        self.logout_url = reverse("accounts:logout")

    def test_a_get_never_signs_the_employee_out(self):
        self.login(self.admin)
        response = self.client.get(self.logout_url)
        self.assertRedirects(response, reverse("dashboard:home"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_a_post_ends_the_session(self):
        self.login(self.admin)
        response = self.client.post(self.logout_url)
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_signing_out_records_a_logout_entry(self):
        self.login(self.admin)
        self.client.post(self.logout_url)
        self.assertTrue(
            ActivityLog.objects.filter(
                user=self.admin, action=ActivityLog.LOGOUT
            ).exists()
        )

    def test_anonymous_visitors_are_sent_to_sign_in(self):
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])


class ProfileViewTests(RailCoreTestCase):
    def setUp(self):
        self.url = reverse("accounts:profile")
        self.password_url = reverse("accounts:password_change")

    def _payload(self, **overrides):
        payload = {
            "first_name": "Neha",
            "last_name": "Verma",
            "email": "neha.verma@railcore.example",
            "phone": "+91 98765 43210",
        }
        payload.update(overrides)
        return payload

    def test_every_role_can_open_their_own_profile(self):
        for user in (
            self.admin,
            self.railway_manager,
            self.station_manager,
            self.operations_staff,
        ):
            with self.subTest(role=user.role_name):
                self.assertAllowed(self.url, user)

    def test_the_profile_lists_what_the_role_may_do(self):
        response = self.assertAllowed(self.url, self.station_manager)
        modules = {row["module"]: row for row in response.context["capabilities"]}
        self.assertTrue(modules["platforms"]["can_manage"])
        self.assertFalse(modules["trains"]["can_view"])
        self.assertEqual(modules["schedules"]["access_label"], "View only")

    def test_an_employee_can_update_their_own_details(self):
        self.login(self.operations_staff)
        response = self.client.post(self.url, self._payload())
        self.assertRedirects(response, self.url)

        self.operations_staff.refresh_from_db()
        self.assertEqual(self.operations_staff.first_name, "Neha")
        self.assertEqual(self.operations_staff.phone, "+91 98765 43210")

    def test_updating_the_profile_is_recorded_in_the_audit_trail(self):
        self.login(self.operations_staff)
        self.client.post(self.url, self._payload())
        self.assertTrue(
            ActivityLog.objects.filter(
                user=self.operations_staff,
                action=ActivityLog.UPDATE,
                description__icontains="own profile",
            ).exists()
        )

    def test_the_profile_form_never_exposes_the_role_or_username(self):
        fields = ProfileForm().fields
        self.assertNotIn("role", fields)
        self.assertNotIn("username", fields)
        self.assertNotIn("is_active", fields)

    def test_posting_a_role_through_the_profile_changes_nothing(self):
        original_username = self.operations_staff.username
        self.login(self.operations_staff)
        self.client.post(
            self.url,
            self._payload(role=self.admin.role_id, username="root", is_active=True),
        )

        self.operations_staff.refresh_from_db()
        self.assertEqual(self.operations_staff.role.name, Role.OPERATIONS_STAFF)
        self.assertEqual(self.operations_staff.username, original_username)

    def test_an_invalid_phone_number_redisplays_the_form(self):
        self.login(self.operations_staff)
        response = self.client.post(self.url, self._payload(phone="not a phone"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("phone", response.context["form"].errors)

    def test_an_email_used_by_another_account_is_rejected(self):
        self.login(self.operations_staff)
        response = self.client.post(self.url, self._payload(email=self.admin.email))
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)

    def test_keeping_your_own_email_is_allowed(self):
        form = ProfileForm(
            data=self._payload(email=self.operations_staff.email),
            instance=self.operations_staff,
        )
        self.assertTrue(form.is_valid(), form.errors)


class PasswordChangeTests(RailCoreTestCase):
    def setUp(self):
        self.url = reverse("accounts:password_change")
        self.new_password = "Corridor#8821"

    def _payload(self, **overrides):
        payload = {
            "old_password": PASSWORD,
            "new_password1": self.new_password,
            "new_password2": self.new_password,
        }
        payload.update(overrides)
        return payload

    def test_an_employee_can_change_their_own_password(self):
        self.login(self.operations_staff)
        response = self.client.post(self.url, self._payload())
        self.assertRedirects(response, reverse("accounts:profile"))

        self.operations_staff.refresh_from_db()
        self.assertTrue(self.operations_staff.check_password(self.new_password))

    def test_the_session_survives_the_change(self):
        self.login(self.operations_staff)
        self.client.post(self.url, self._payload())
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)

    def test_the_new_password_signs_the_employee_back_in(self):
        self.login(self.operations_staff)
        self.client.post(self.url, self._payload())
        self.client.logout()
        self.assertTrue(
            self.client.login(
                username=self.operations_staff.username, password=self.new_password
            )
        )

    def test_the_change_is_recorded_in_the_audit_trail(self):
        self.login(self.operations_staff)
        self.client.post(self.url, self._payload())
        self.assertTrue(
            ActivityLog.objects.filter(
                user=self.operations_staff, description__icontains="password"
            ).exists()
        )

    def test_a_wrong_current_password_is_refused(self):
        self.login(self.operations_staff)
        response = self.client.post(self.url, self._payload(old_password="nope"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("old_password", response.context["form"].errors)

        self.operations_staff.refresh_from_db()
        self.assertTrue(self.operations_staff.check_password(PASSWORD))

    def test_mismatched_new_passwords_are_refused(self):
        self.login(self.operations_staff)
        response = self.client.post(self.url, self._payload(new_password2="Different#99"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("new_password2", response.context["form"].errors)

    def test_a_weak_password_is_refused(self):
        self.login(self.operations_staff)
        response = self.client.post(
            self.url, self._payload(new_password1="12345678", new_password2="12345678")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("new_password2", response.context["form"].errors)


class UserFormTests(RailCoreTestCase):
    def _payload(self, **overrides):
        payload = {
            "username": "n.verma",
            "first_name": "Neha",
            "last_name": "Verma",
            "email": "n.verma@railcore.example",
            "role": self.operations_staff.role_id,
            "phone": "+91 90000 11111",
            "password1": "Platform#9034",
            "password2": "Platform#9034",
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_is_accepted(self):
        self.assertTrue(UserCreateForm(data=self._payload()).is_valid())

    def test_the_password_is_stored_hashed(self):
        form = UserCreateForm(data=self._payload())
        self.assertTrue(form.is_valid(), form.errors)
        account = form.save()

        self.assertNotEqual(account.password, "Platform#9034")
        self.assertTrue(account.check_password("Platform#9034"))

    def test_mismatched_passwords_are_rejected(self):
        form = UserCreateForm(data=self._payload(password2="Something#Else1"))
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["password2"], ["The two passwords do not match."]
        )

    def test_a_weak_password_is_rejected(self):
        form = UserCreateForm(data=self._payload(password1="password", password2="password"))
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_a_password_that_looks_like_the_username_is_rejected(self):
        form = UserCreateForm(data=self._payload(password1="n.verma2026", password2="n.verma2026"))
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_a_duplicate_username_is_rejected(self):
        form = UserCreateForm(data=self._payload(username=self.admin.username))
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    def test_a_duplicate_email_is_rejected(self):
        form = UserCreateForm(data=self._payload(email=self.admin.email.upper()))
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors["email"], ["Another account already uses this email address."]
        )

    def test_an_email_freed_by_a_deleted_account_can_be_reused(self):
        leaver = create_user("leaver", email="shared@railcore.example")
        leaver.soft_delete()
        self.assertTrue(UserCreateForm(data=self._payload(email="shared@railcore.example")).is_valid())

    def test_required_fields_are_enforced(self):
        form = UserCreateForm(data={})
        self.assertFalse(form.is_valid())
        for field in ("username", "email", "password1", "password2"):
            self.assertIn(field, form.errors)

    def test_only_active_roles_are_offered(self):
        retired = Role.objects.create(name="Retired Role", is_active=False)
        self.assertNotIn(retired, UserCreateForm().fields["role"].queryset)

    def test_the_update_form_never_asks_for_a_password(self):
        fields = UserUpdateForm(instance=self.admin).fields
        self.assertNotIn("password1", fields)
        self.assertNotIn("password", fields)
        self.assertIn("role", fields)
        self.assertIn("is_active", fields)

    def test_editing_keeps_the_accounts_own_email(self):
        form = UserUpdateForm(
            data={
                "username": self.railway_manager.username,
                "first_name": self.railway_manager.first_name,
                "last_name": self.railway_manager.last_name,
                "email": self.railway_manager.email,
                "role": self.railway_manager.role_id,
                "phone": "",
                "is_active": True,
            },
            instance=self.railway_manager,
        )
        self.assertTrue(form.is_valid(), form.errors)


class UserAdministrationTests(RailCoreTestCase):
    def setUp(self):
        self.list_url = reverse("accounts:user_list")
        self.add_url = reverse("accounts:user_add")
        self.detail_url = reverse("accounts:user_detail", args=[self.operations_staff.pk])
        self.edit_url = reverse("accounts:user_edit", args=[self.operations_staff.pk])
        self.delete_url = reverse("accounts:user_delete", args=[self.operations_staff.pk])
        self.restore_url = reverse("accounts:user_restore", args=[self.operations_staff.pk])

    def _payload(self, **overrides):
        payload = {
            "username": "n.verma",
            "first_name": "Neha",
            "last_name": "Verma",
            "email": "n.verma@railcore.example",
            "role": self.operations_staff.role_id,
            "phone": "+91 90000 11111",
            "password1": "Platform#9034",
            "password2": "Platform#9034",
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    def _edit_payload(self, **overrides):
        account = self.operations_staff
        payload = {
            "username": account.username,
            "first_name": account.first_name,
            "last_name": account.last_name,
            "email": account.email,
            "role": account.role_id,
            "phone": "",
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    # -- access --------------------------------------------------------
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_only_the_administrator_may_open_the_directory(self):
        self.assertAllowed(self.list_url, self.admin)
        for user in (self.railway_manager, self.station_manager, self.operations_staff):
            with self.subTest(role=user.role_name):
                self.assertForbidden(self.list_url, user)

    def test_non_administrators_cannot_open_an_account(self):
        self.assertForbidden(self.detail_url, self.railway_manager)

    def test_non_administrators_cannot_add_an_account(self):
        self.assertForbidden(self.add_url, self.railway_manager)

    def test_non_administrators_cannot_edit_an_account(self):
        self.assertForbidden(self.edit_url, self.station_manager)

    def test_non_administrators_cannot_delete_an_account(self):
        self.assertForbidden(self.delete_url, self.operations_staff)

    # -- create --------------------------------------------------------
    def test_the_administrator_can_open_an_account(self):
        self.login(self.admin)
        response = self.client.post(self.add_url, self._payload())
        self.assertEqual(response.status_code, 302)

        account = User.objects.get(username="n.verma")
        self.assertEqual(account.role.name, Role.OPERATIONS_STAFF)
        self.assertTrue(account.check_password("Platform#9034"))

    def test_the_new_account_can_sign_in(self):
        self.login(self.admin)
        self.client.post(self.add_url, self._payload())
        self.client.logout()
        self.assertTrue(self.client.login(username="n.verma", password="Platform#9034"))

    def test_creating_an_account_writes_an_activity_log_entry(self):
        self.login(self.admin)
        self.client.post(self.add_url, self._payload())
        self.assertTrue(
            ActivityLog.objects.filter(
                action=ActivityLog.CREATE,
                model_name="User",
                description__icontains="n.verma",
            ).exists()
        )

    def test_creating_an_account_notifies_the_other_administrators(self):
        other_admin = create_user("second_admin", role_name=Role.ADMIN)
        self.login(self.admin)
        self.client.post(self.add_url, self._payload())

        self.assertTrue(
            Notification.objects.filter(
                user=other_admin, title="New user account created"
            ).exists()
        )
        self.assertFalse(Notification.objects.filter(user=self.admin).exists())

    def test_a_duplicate_username_redisplays_the_form(self):
        self.login(self.admin)
        response = self.client.post(
            self.add_url, self._payload(username=self.admin.username)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)

    # -- read ----------------------------------------------------------
    def test_the_detail_page_summarises_the_account(self):
        self.login(self.admin)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.operations_staff.username)
        self.assertEqual(response.context["account"], self.operations_staff)

    def test_the_detail_page_counts_the_notifications_raised_for_the_account(self):
        Notification.objects.create(
            user=self.operations_staff, title="Read me", message="Body"
        )
        Notification.objects.create(
            user=self.operations_staff, title="Seen", message="Body", is_read=True
        )
        self.login(self.admin)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.context["notification_count"], 2)
        self.assertEqual(response.context["unread_count"], 1)

    def test_a_missing_account_returns_404(self):
        self.login(self.admin)
        response = self.client.get(reverse("accounts:user_detail", args=[999999]))
        self.assertEqual(response.status_code, 404)

    # -- update --------------------------------------------------------
    def test_the_administrator_can_change_a_role(self):
        self.login(self.admin)
        response = self.client.post(
            self.edit_url, self._edit_payload(role=self.station_manager.role_id)
        )
        self.assertRedirects(response, self.detail_url)

        self.operations_staff.refresh_from_db()
        self.assertEqual(self.operations_staff.role.name, Role.STATION_MANAGER)

    def test_changing_a_role_changes_what_the_employee_may_open(self):
        self.login(self.admin)
        self.client.post(self.edit_url, self._edit_payload(role=self.admin.role_id))
        self.client.logout()

        self.assertAllowed(self.list_url, self.operations_staff)

    def test_the_administrator_can_deactivate_an_account(self):
        self.login(self.admin)
        payload = self._edit_payload()
        payload.pop("is_active")
        self.client.post(self.edit_url, payload)

        self.operations_staff.refresh_from_db()
        self.assertFalse(self.operations_staff.is_active)
        self.assertFalse(self.operations_staff.is_deleted)

    def test_editing_an_account_writes_an_activity_log_entry(self):
        self.login(self.admin)
        self.client.post(self.edit_url, self._edit_payload(first_name="Renamed"))
        self.assertTrue(
            ActivityLog.objects.filter(
                action=ActivityLog.UPDATE, model_name="User"
            ).exists()
        )

    def test_a_duplicate_email_redisplays_the_form(self):
        self.login(self.admin)
        response = self.client.post(
            self.edit_url, self._edit_payload(email=self.admin.email)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)

    # -- soft delete and restore ---------------------------------------
    def test_delete_shows_a_confirmation_before_acting(self):
        self.login(self.admin)
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["soft_delete"])
        self.assertTrue(User.active_objects.filter(pk=self.operations_staff.pk).exists())

    def test_post_soft_deletes_the_account(self):
        self.login(self.admin)
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, self.list_url)

        self.operations_staff.refresh_from_db()
        self.assertTrue(self.operations_staff.is_deleted)
        self.assertFalse(self.operations_staff.is_active)
        self.assertTrue(User.objects.filter(pk=self.operations_staff.pk).exists())

    def test_a_deleted_account_keeps_its_audit_trail(self):
        self.login(self.operations_staff)
        self.client.logout()
        entries = ActivityLog.objects.filter(user=self.operations_staff).count()
        self.assertTrue(entries)

        self.login(self.admin)
        self.client.post(self.delete_url)
        self.assertEqual(
            ActivityLog.objects.filter(user=self.operations_staff).count(), entries
        )

    def test_the_administrator_cannot_delete_their_own_account(self):
        self.login(self.admin)
        response = self.client.post(
            reverse("accounts:user_delete", args=[self.admin.pk])
        )
        self.assertRedirects(response, self.list_url)
        self.assertIn(
            "You cannot delete the account you are signed in with.", _messages(response)
        )

        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_deleted)

    def test_a_second_administrator_can_be_deleted(self):
        spare = create_user("spare_admin", role_name=Role.ADMIN)
        self.login(self.admin)
        self.client.post(reverse("accounts:user_delete", args=[spare.pk]))

        spare.refresh_from_db()
        self.assertTrue(spare.is_deleted)

    def test_restore_needs_a_post(self):
        self.operations_staff.soft_delete()
        self.login(self.admin)
        response = self.client.get(self.restore_url)
        self.assertEqual(response.status_code, 405)

    def test_a_deleted_account_can_be_restored(self):
        self.operations_staff.soft_delete()
        self.login(self.admin)
        response = self.client.post(self.restore_url)
        self.assertRedirects(response, self.detail_url)

        self.operations_staff.refresh_from_db()
        self.assertFalse(self.operations_staff.is_deleted)
        self.assertTrue(self.operations_staff.is_active)

    def test_a_restored_employee_can_sign_in_again(self):
        self.operations_staff.soft_delete()
        self.login(self.admin)
        self.client.post(self.restore_url)
        self.client.logout()

        self.assertTrue(
            self.client.login(
                username=self.operations_staff.username, password=PASSWORD
            )
        )

    def test_restoring_a_live_account_is_a_harmless_no_op(self):
        self.login(self.admin)
        response = self.client.post(self.restore_url)
        self.assertEqual(response.status_code, 302)

        self.operations_staff.refresh_from_db()
        self.assertFalse(self.operations_staff.is_deleted)

    def test_non_administrators_cannot_restore_an_account(self):
        self.operations_staff.soft_delete()
        self.assertForbidden(self.restore_url, self.railway_manager, method="post")

    # -- directory behaviour -------------------------------------------
    def test_the_directory_hides_deleted_accounts_by_default(self):
        self.operations_staff.soft_delete()
        response = self.assertAllowed(self.list_url, self.admin)
        self.assertNotIn(self.operations_staff, list(response.context["users"]))

    def test_the_deleted_filter_reveals_them(self):
        self.operations_staff.soft_delete()
        self.login(self.admin)
        response = self.client.get(self.list_url, {"status": "deleted"})
        self.assertEqual(list(response.context["users"]), [self.operations_staff])

    def test_the_inactive_filter_lists_only_disabled_accounts(self):
        self.railway_manager.is_active = False
        self.railway_manager.save(update_fields=["is_active"])
        self.login(self.admin)
        response = self.client.get(self.list_url, {"status": "inactive"})
        self.assertEqual(list(response.context["users"]), [self.railway_manager])

    def test_the_role_filter_narrows_the_directory(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"role": Role.STATION_MANAGER})
        roles = {account.role.name for account in response.context["users"]}
        self.assertEqual(roles, {Role.STATION_MANAGER})

    def test_search_matches_the_username(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"q": self.station_manager.username})
        self.assertEqual(list(response.context["users"]), [self.station_manager])

    def test_the_count_comes_from_the_database(self):
        self.login(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.context["total_count"], User.active_objects.count())

    def test_sorting_by_a_whitelisted_column(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"sort": "-username"})
        usernames = [account.username for account in response.context["users"]]
        self.assertEqual(usernames, sorted(usernames, reverse=True))

    def test_unknown_sort_value_falls_back_to_the_default(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"sort": "password"})
        self.assertEqual(response.status_code, 200)
        usernames = [account.username for account in response.context["users"]]
        self.assertEqual(usernames, sorted(usernames))

    def test_a_filtered_view_with_no_matches_renders_an_empty_state(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"q": "nobody-by-this-name"})
        self.assertContains(response, "No employees match this view")


class ActiveAdminCountTests(RailCoreTestCase):
    """The guard that keeps at least one administrator able to sign in."""

    def test_the_seeded_administrator_is_counted(self):
        self.assertEqual(_active_admin_count(), 1)

    def test_the_account_being_removed_can_be_excluded(self):
        self.assertEqual(_active_admin_count(exclude_pk=self.admin.pk), 0)

    def test_a_deleted_administrator_is_not_counted(self):
        spare = create_user("spare_admin", role_name=Role.ADMIN)
        self.assertEqual(_active_admin_count(), 2)

        spare.soft_delete()
        self.assertEqual(_active_admin_count(), 1)

    def test_a_deactivated_administrator_is_not_counted(self):
        spare = create_user("spare_admin", role_name=Role.ADMIN, is_active=False)
        self.assertEqual(_active_admin_count(), 1)
        self.assertIsNotNone(spare.pk)

    def test_a_superuser_without_a_role_still_counts(self):
        create_user("root", is_superuser=True, is_staff=True)
        self.assertEqual(_active_admin_count(), 2)

    def test_other_roles_are_never_counted(self):
        create_user("extra_ops", role_name=Role.OPERATIONS_STAFF)
        self.assertEqual(_active_admin_count(), 1)
