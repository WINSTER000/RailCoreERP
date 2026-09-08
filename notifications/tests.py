"""Notification centre tests: per-employee scoping, filters and the nav badge."""

from django.urls import reverse

from accounts.factories import RailCoreTestCase
from notifications.services import notify_all, notify_roles, notify_users, unread_count

from .models import Notification


class NotificationModelTests(RailCoreTestCase):
    def test_string_is_the_title(self):
        notification = Notification.objects.create(
            user=self.admin, title="Train 12951 delayed", message="45 minutes"
        )
        self.assertEqual(str(notification), "Train 12951 delayed")

    def test_the_icon_follows_the_level(self):
        levels = {
            Notification.INFO: "info",
            Notification.SUCCESS: "check",
            Notification.WARNING: "alert",
            Notification.DANGER: "ban",
        }
        for level, icon in levels.items():
            with self.subTest(level=level):
                notification = Notification(level=level)
                self.assertEqual(notification.icon, icon)

    def test_mark_read_is_idempotent(self):
        notification = Notification.objects.create(
            user=self.admin, title="Read me", message="Body"
        )
        notification.mark_read()
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

        notification.mark_read()
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_newest_notifications_come_first(self):
        first = Notification.objects.create(user=self.admin, title="First", message="a")
        second = Notification.objects.create(user=self.admin, title="Second", message="b")
        self.assertEqual(list(Notification.objects.all()), [second, first])

    def test_deleting_an_account_removes_its_notifications(self):
        spare = self.railway_manager
        Notification.objects.create(user=spare, title="Bye", message="Body")
        spare.delete()
        self.assertEqual(Notification.objects.count(), 0)


class NotificationServiceTests(RailCoreTestCase):
    def test_notify_users_writes_one_row_each(self):
        created = notify_users(
            [self.admin, self.operations_staff], "Heads up", "Something happened"
        )
        self.assertEqual(created, 2)
        self.assertEqual(Notification.objects.count(), 2)

    def test_notify_users_ignores_an_empty_audience(self):
        self.assertEqual(notify_users([], "Nobody", "Body"), 0)
        self.assertEqual(notify_users([None], "Nobody", "Body"), 0)

    def test_notify_roles_always_includes_the_administrators(self):
        notify_roles(
            ["Operations Staff"], "Timetable changed", "A run was rescheduled."
        )
        recipients = set(
            Notification.objects.values_list("user__username", flat=True)
        )
        self.assertEqual(
            recipients, {self.admin.username, self.operations_staff.username}
        )

    def test_notify_roles_can_skip_the_author(self):
        notify_roles(
            ["Operations Staff"],
            "Timetable changed",
            "A run was rescheduled.",
            exclude=self.operations_staff,
        )
        recipients = set(Notification.objects.values_list("user__username", flat=True))
        self.assertEqual(recipients, {self.admin.username})

    def test_notify_roles_skips_deleted_and_disabled_accounts(self):
        self.operations_staff.soft_delete()
        self.railway_manager.is_active = False
        self.railway_manager.save(update_fields=["is_active"])

        notify_roles(
            ["Operations Staff", "Railway Manager"], "Network notice", "Body"
        )
        recipients = set(Notification.objects.values_list("user__username", flat=True))
        self.assertEqual(recipients, {self.admin.username})

    def test_notify_all_reaches_every_active_employee(self):
        self.assertEqual(notify_all("Maintenance window", "Body"), 4)

    def test_notify_all_can_skip_the_author(self):
        self.assertEqual(notify_all("Maintenance window", "Body", exclude=self.admin), 3)
        self.assertFalse(Notification.objects.filter(user=self.admin).exists())

    def test_the_level_is_carried_through(self):
        notify_users([self.admin], "Cancelled", "Body", level=Notification.DANGER)
        self.assertEqual(Notification.objects.get().level, Notification.DANGER)

    def test_a_long_title_is_truncated_to_fit_the_column(self):
        notify_users([self.admin], "T" * 200, "Body")
        self.assertEqual(len(Notification.objects.get().title), 140)

    def test_unread_count_is_per_employee(self):
        Notification.objects.create(user=self.admin, title="Mine", message="Body")
        Notification.objects.create(
            user=self.admin, title="Seen", message="Body", is_read=True
        )
        Notification.objects.create(
            user=self.operations_staff, title="Theirs", message="Body"
        )

        self.assertEqual(unread_count(self.admin), 1)
        self.assertEqual(unread_count(self.operations_staff), 1)

    def test_unread_count_of_an_anonymous_visitor_is_zero(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(unread_count(AnonymousUser()), 0)
        self.assertEqual(unread_count(None), 0)


class NotificationListTests(RailCoreTestCase):
    def setUp(self):
        self.url = reverse("notifications:list")
        self.mine = Notification.objects.create(
            user=self.operations_staff,
            title="Train 12951 was cancelled",
            message="Rake unavailable",
            level=Notification.DANGER,
        )
        self.read = Notification.objects.create(
            user=self.operations_staff,
            title="Train 12002 delayed 20 minutes",
            message="Signal failure",
            level=Notification.WARNING,
            is_read=True,
        )
        self.theirs = Notification.objects.create(
            user=self.admin, title="Not for operations", message="Body"
        )

    def test_anonymous_visitors_are_sent_to_sign_in(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_every_role_has_a_notification_centre(self):
        for user in (
            self.admin,
            self.railway_manager,
            self.station_manager,
            self.operations_staff,
        ):
            with self.subTest(role=user.role_name):
                self.assertAllowed(self.url, user)

    def test_an_employee_only_sees_their_own_notifications(self):
        self.login(self.operations_staff)
        listed = list(self.client.get(self.url).context["notifications"])
        self.assertEqual(listed, [self.read, self.mine])
        self.assertNotIn(self.theirs, listed)

    def test_the_unread_total_ignores_the_filters(self):
        self.login(self.operations_staff)
        response = self.client.get(self.url, {"read": "read"})
        self.assertEqual(response.context["unread_total"], 1)
        self.assertEqual(response.context["total_count"], 1)

    def test_the_unread_filter_narrows_the_list(self):
        self.login(self.operations_staff)
        response = self.client.get(self.url, {"read": "unread"})
        self.assertEqual(list(response.context["notifications"]), [self.mine])

    def test_the_level_filter_narrows_the_list(self):
        self.login(self.operations_staff)
        response = self.client.get(self.url, {"level": "danger"})
        self.assertEqual(list(response.context["notifications"]), [self.mine])
        self.assertEqual(response.context["level_filter"], Notification.DANGER)

    def test_a_bogus_level_is_ignored(self):
        self.login(self.operations_staff)
        response = self.client.get(self.url, {"level": "'; drop table"})
        self.assertEqual(response.context["level_filter"], "")
        self.assertEqual(response.context["total_count"], 2)

    def test_a_bogus_read_state_is_ignored(self):
        self.login(self.operations_staff)
        response = self.client.get(self.url, {"read": "maybe"})
        self.assertEqual(response.context["read_filter"], "")
        self.assertEqual(response.context["total_count"], 2)

    def test_the_subtitle_counts_what_is_on_screen(self):
        self.login(self.operations_staff)
        response = self.client.get(self.url)
        self.assertEqual(
            response.context["page_subtitle"],
            "2 notifications in this view, 1 still unread",
        )

    def test_the_subtitle_celebrates_a_clean_inbox(self):
        self.mine.mark_read()
        self.login(self.operations_staff)
        response = self.client.get(self.url)
        self.assertEqual(
            response.context["page_subtitle"], "2 notifications in this view, all read"
        )

    def test_an_empty_inbox_renders_an_empty_state(self):
        response = self.assertAllowed(self.url, self.station_manager)
        self.assertContains(response, "You are all caught up")

    def test_a_filtered_view_with_no_matches_renders_an_empty_state(self):
        self.login(self.operations_staff)
        response = self.client.get(self.url, {"level": "success"})
        self.assertContains(response, "Nothing matches this view")


class NotificationActionTests(RailCoreTestCase):
    def setUp(self):
        self.list_url = reverse("notifications:list")
        self.notification = Notification.objects.create(
            user=self.operations_staff,
            title="Train 12951 was cancelled",
            message="Rake unavailable",
            url=reverse("railway:schedule_list"),
        )
        self.read_url = reverse("notifications:mark_read", args=[self.notification.pk])
        self.delete_url = reverse("notifications:delete", args=[self.notification.pk])
        self.read_all_url = reverse("notifications:mark_all_read")

    # -- mark one as read ----------------------------------------------
    def test_marking_as_read_needs_a_post(self):
        self.login(self.operations_staff)
        self.assertEqual(self.client.get(self.read_url).status_code, 405)

        self.notification.refresh_from_db()
        self.assertFalse(self.notification.is_read)

    def test_reading_a_notification_opens_the_record_it_points_at(self):
        self.login(self.operations_staff)
        response = self.client.post(self.read_url)
        self.assertRedirects(response, reverse("railway:schedule_list"))

        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)

    def test_a_notification_without_a_link_returns_to_the_list(self):
        plain = Notification.objects.create(
            user=self.operations_staff, title="No link", message="Body"
        )
        self.login(self.operations_staff)
        response = self.client.post(reverse("notifications:mark_read", args=[plain.pk]))
        self.assertRedirects(response, self.list_url)

    def test_an_offsite_link_is_refused(self):
        hijacked = Notification.objects.create(
            user=self.operations_staff,
            title="Suspicious",
            message="Body",
            url="https://phishing.example.com/steal",
        )
        self.login(self.operations_staff)
        response = self.client.post(
            reverse("notifications:mark_read", args=[hijacked.pk])
        )
        self.assertRedirects(response, self.list_url)

    def test_one_employee_cannot_read_another_employees_notification(self):
        self.login(self.railway_manager)
        self.assertEqual(self.client.post(self.read_url).status_code, 404)

        self.notification.refresh_from_db()
        self.assertFalse(self.notification.is_read)

    # -- mark everything as read ---------------------------------------
    def test_mark_all_read_needs_a_post(self):
        self.login(self.operations_staff)
        self.assertEqual(self.client.get(self.read_all_url).status_code, 405)

    def test_mark_all_read_clears_only_this_employees_queue(self):
        Notification.objects.create(
            user=self.operations_staff, title="Second", message="Body"
        )
        theirs = Notification.objects.create(
            user=self.admin, title="Not mine", message="Body"
        )

        self.login(self.operations_staff)
        response = self.client.post(self.read_all_url)
        self.assertRedirects(response, self.list_url)

        self.assertEqual(
            Notification.objects.filter(
                user=self.operations_staff, is_read=False
            ).count(),
            0,
        )
        theirs.refresh_from_db()
        self.assertFalse(theirs.is_read)

    def test_mark_all_read_on_a_clean_inbox_is_harmless(self):
        self.login(self.station_manager)
        response = self.client.post(self.read_all_url)
        self.assertRedirects(response, self.list_url)

    # -- delete ---------------------------------------------------------
    def test_deleting_needs_a_post(self):
        self.login(self.operations_staff)
        self.assertEqual(self.client.get(self.delete_url).status_code, 405)
        self.assertTrue(Notification.objects.filter(pk=self.notification.pk).exists())

    def test_an_employee_can_delete_their_own_notification(self):
        self.login(self.operations_staff)
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, self.list_url)
        self.assertFalse(Notification.objects.filter(pk=self.notification.pk).exists())

    def test_one_employee_cannot_delete_another_employees_notification(self):
        self.login(self.admin)
        self.assertEqual(self.client.post(self.delete_url).status_code, 404)
        self.assertTrue(Notification.objects.filter(pk=self.notification.pk).exists())


class NotificationBadgeTests(RailCoreTestCase):
    def test_the_header_badge_counts_the_unread_queue(self):
        Notification.objects.create(
            user=self.operations_staff, title="Unread", message="Body"
        )
        Notification.objects.create(
            user=self.operations_staff, title="Seen", message="Body", is_read=True
        )
        Notification.objects.create(user=self.admin, title="Theirs", message="Body")

        self.login(self.operations_staff)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.context["unread_notification_count"], 1)
        self.assertEqual(len(response.context["header_notifications"]), 1)

    def test_the_badge_preview_is_capped_at_five(self):
        for index in range(7):
            Notification.objects.create(
                user=self.operations_staff, title=f"Notice {index}", message="Body"
            )
        self.login(self.operations_staff)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.context["unread_notification_count"], 7)
        self.assertEqual(len(response.context["header_notifications"]), 5)

    def test_the_badge_drops_to_zero_once_everything_is_read(self):
        Notification.objects.create(
            user=self.operations_staff, title="Unread", message="Body"
        )
        self.login(self.operations_staff)
        self.client.post(reverse("notifications:mark_all_read"))

        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.context["unread_notification_count"], 0)

    def test_anonymous_pages_carry_an_empty_badge(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.context["unread_notification_count"], 0)
        self.assertEqual(response.context["header_notifications"], [])
