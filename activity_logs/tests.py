"""Audit trail tests: entries are written automatically and read by managers."""

from django.urls import reverse

from accounts.factories import RailCoreTestCase, create_user
from accounts.models import Role
from railway.factories import create_station, create_train

from .models import ActivityLog
from .services import (
    log_activity,
    log_create,
    log_delete,
    log_update,
    recent_activity,
)


class ActivityLogModelTests(RailCoreTestCase):
    def test_string_names_the_actor_action_and_model(self):
        entry = ActivityLog.objects.create(
            user=self.admin,
            action=ActivityLog.CREATE,
            model_name="Station",
            object_id="7",
        )
        self.assertEqual(str(entry), f"{self.admin.display_name} · CREATE · Station")

    def test_a_systemwide_entry_reads_as_system(self):
        entry = ActivityLog.objects.create(user=None, action=ActivityLog.UPDATE)
        self.assertEqual(str(entry), "System · UPDATE · -")
        self.assertEqual(entry.actor_name, "System")
        self.assertEqual(entry.actor_initials, "SY")

    def test_the_icon_follows_the_action(self):
        for action, icon in ActivityLog.ACTION_ICONS.items():
            with self.subTest(action=action):
                self.assertEqual(ActivityLog(action=action).icon, icon)

    def test_the_target_combines_the_model_and_id(self):
        self.assertEqual(
            ActivityLog(model_name="Train", object_id="12").target, "Train #12"
        )
        self.assertEqual(ActivityLog(model_name="Train").target, "Train")
        self.assertEqual(ActivityLog().target, "-")

    def test_newest_entries_come_first(self):
        first = ActivityLog.objects.create(user=self.admin, action=ActivityLog.CREATE)
        second = ActivityLog.objects.create(user=self.admin, action=ActivityLog.UPDATE)
        self.assertEqual(list(ActivityLog.objects.all())[:2], [second, first])

    def test_deleting_an_account_keeps_the_trail(self):
        ActivityLog.objects.create(user=self.railway_manager, action=ActivityLog.LOGIN)
        self.railway_manager.delete()

        entry = ActivityLog.objects.get()
        self.assertIsNone(entry.user)
        self.assertEqual(entry.actor_name, "System")


class ActivityLogServiceTests(RailCoreTestCase):
    def test_log_activity_derives_the_target_from_an_instance(self):
        station = create_station(name="Kota Junction", station_code="KOTA")
        entry = log_activity(self.admin, ActivityLog.CREATE, instance=station)

        self.assertEqual(entry.model_name, "Station")
        self.assertEqual(entry.object_id, str(station.pk))
        self.assertEqual(entry.description, str(station))

    def test_the_three_shortcuts_record_their_action(self):
        station = create_station()
        self.assertEqual(log_create(self.admin, station).action, ActivityLog.CREATE)
        self.assertEqual(log_update(self.admin, station).action, ActivityLog.UPDATE)
        self.assertEqual(log_delete(self.admin, station).action, ActivityLog.DELETE)

    def test_a_default_description_is_written_when_none_is_given(self):
        train = create_train(train_number="12951", train_name="Mumbai Rajdhani")
        entry = log_create(self.admin, train)
        self.assertEqual(entry.description, "Created Train 12951 - Mumbai Rajdhani")

    def test_an_anonymous_actor_is_stored_as_no_user(self):
        from django.contrib.auth.models import AnonymousUser

        entry = log_activity(AnonymousUser(), ActivityLog.LOGIN, model_name="User")
        self.assertIsNone(entry.user)

    def test_a_long_description_is_truncated_to_fit_the_column(self):
        entry = log_activity(self.admin, ActivityLog.UPDATE, description="D" * 400)
        self.assertEqual(len(entry.description), 255)

    def test_a_missing_object_id_is_stored_as_an_empty_string(self):
        entry = log_activity(self.admin, ActivityLog.LOGIN, model_name="User")
        self.assertEqual(entry.object_id, "")

    def test_recent_activity_returns_the_newest_entries_only(self):
        for index in range(10):
            ActivityLog.objects.create(
                user=self.admin, action=ActivityLog.CREATE, description=f"Entry {index}"
            )
        entries = recent_activity()
        self.assertEqual(len(entries), 8)
        self.assertEqual(entries[0].description, "Entry 9")


class ActivityLogGenerationTests(RailCoreTestCase):
    """The audit trail fills itself as employees work."""

    def test_signing_in_and_out_is_recorded(self):
        self.login(self.railway_manager)
        self.client.post(reverse("accounts:logout"))

        actions = list(
            ActivityLog.objects.filter(user=self.railway_manager).values_list(
                "action", flat=True
            )
        )
        self.assertEqual(actions, [ActivityLog.LOGOUT, ActivityLog.LOGIN])

    def test_creating_a_record_is_recorded(self):
        self.login(self.station_manager)
        self.client.post(
            reverse("railway:station_add"),
            {
                "name": "Kota Junction",
                "station_code": "KOTA",
                "city": "Kota",
                "state": "Rajasthan",
                "is_active": True,
            },
        )
        entry = ActivityLog.objects.filter(action=ActivityLog.CREATE).get()
        self.assertEqual(entry.user, self.station_manager)
        self.assertEqual(entry.model_name, "Station")
        self.assertIn("KOTA", entry.description)

    def test_editing_a_record_is_recorded(self):
        station = create_station(name="Kota Junction", station_code="KOTA")
        self.login(self.station_manager)
        self.client.post(
            reverse("railway:station_edit", args=[station.pk]),
            {
                "name": "Kota Jn",
                "station_code": "KOTA",
                "city": "Kota",
                "state": "Rajasthan",
                "is_active": True,
            },
        )
        self.assertTrue(
            ActivityLog.objects.filter(
                action=ActivityLog.UPDATE, model_name="Station"
            ).exists()
        )

    def test_deleting_a_record_is_recorded(self):
        station = create_station(name="Kota Junction", station_code="KOTA")
        self.login(self.station_manager)
        self.client.post(reverse("railway:station_delete", args=[station.pk]))

        entry = ActivityLog.objects.filter(action=ActivityLog.DELETE).get()
        self.assertEqual(entry.model_name, "Station")
        self.assertEqual(entry.object_id, str(station.pk))

    def test_the_trail_outlives_the_record_it_describes(self):
        station = create_station(name="Kota Junction", station_code="KOTA")
        self.login(self.station_manager)
        self.client.post(reverse("railway:station_delete", args=[station.pk]))

        self.assertFalse(
            station.__class__.objects.filter(pk=station.pk).exists()
        )
        self.assertTrue(ActivityLog.objects.filter(action=ActivityLog.DELETE).exists())


class ActivityLogViewTests(RailCoreTestCase):
    def setUp(self):
        self.url = reverse("activity_logs:list")
        self.created = ActivityLog.objects.create(
            user=self.railway_manager,
            action=ActivityLog.CREATE,
            model_name="Train",
            object_id="1",
            description="Added train 12951 - Mumbai Rajdhani",
        )
        self.deleted = ActivityLog.objects.create(
            user=self.admin,
            action=ActivityLog.DELETE,
            model_name="Station",
            object_id="4",
            description="Deleted station KOTA",
        )

    # -- access --------------------------------------------------------
    def test_anonymous_visitors_are_sent_to_sign_in(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_administrators_and_railway_managers_may_read_the_trail(self):
        for user in (self.admin, self.railway_manager):
            with self.subTest(role=user.role_name):
                self.assertAllowed(self.url, user)

    def test_other_roles_are_refused(self):
        for user in (self.station_manager, self.operations_staff):
            with self.subTest(role=user.role_name):
                self.assertForbidden(self.url, user)

    def test_an_account_without_a_role_is_refused(self):
        self.assertForbidden(self.url, create_user("no_role_yet"))

    # -- listing -------------------------------------------------------
    def test_the_newest_entry_is_listed_first(self):
        response = self.assertAllowed(self.url, self.admin)
        # Signing in wrote a LOGIN entry, which is the newest of the three.
        first = list(response.context["logs"])[0]
        self.assertEqual(first.action, ActivityLog.LOGIN)
        self.assertIn(self.created, response.context["logs"])

    def test_the_action_filter_narrows_the_trail(self):
        self.login(self.admin)
        response = self.client.get(self.url, {"action": "create"})
        self.assertEqual(list(response.context["logs"]), [self.created])
        self.assertEqual(response.context["action_filter"], ActivityLog.CREATE)

    def test_a_bogus_action_is_ignored(self):
        self.login(self.admin)
        response = self.client.get(self.url, {"action": "'; drop table"})
        self.assertEqual(response.context["action_filter"], "")
        self.assertEqual(response.context["total_count"], 3)

    def test_the_employee_filter_narrows_the_trail(self):
        self.login(self.admin)
        response = self.client.get(self.url, {"user": self.railway_manager.pk})
        self.assertEqual(list(response.context["logs"]), [self.created])
        self.assertEqual(response.context["user_filter"], str(self.railway_manager.pk))

    def test_a_non_numeric_employee_filter_is_ignored(self):
        self.login(self.admin)
        response = self.client.get(self.url, {"user": "admin_user"})
        self.assertEqual(response.context["user_filter"], "")
        self.assertEqual(response.context["total_count"], 3)

    def test_only_employees_who_appear_in_the_trail_are_offered(self):
        self.login(self.admin)
        options = list(self.client.get(self.url).context["user_options"])
        self.assertCountEqual(options, [self.admin, self.railway_manager])

    def test_search_matches_the_description(self):
        self.login(self.admin)
        response = self.client.get(self.url, {"q": "Rajdhani"})
        self.assertEqual(list(response.context["logs"]), [self.created])

    def test_search_matches_the_employee(self):
        self.login(self.admin)
        response = self.client.get(self.url, {"q": self.railway_manager.username})
        self.assertEqual(list(response.context["logs"]), [self.created])

    def test_the_action_summary_counts_the_filtered_view(self):
        self.login(self.admin)
        summary = {
            row["action"]: row for row in self.client.get(self.url).context["action_summary"]
        }
        self.assertEqual(summary[ActivityLog.CREATE]["count"], 1)
        self.assertEqual(summary[ActivityLog.DELETE]["count"], 1)
        self.assertEqual(summary[ActivityLog.LOGIN]["count"], 1)
        self.assertEqual(summary[ActivityLog.CREATE]["percent"], 33.3)

    def test_the_summary_lists_every_action_even_at_zero(self):
        self.login(self.admin)
        response = self.client.get(self.url, {"action": "create"})
        summary = {row["action"]: row["count"] for row in response.context["action_summary"]}
        self.assertEqual(summary[ActivityLog.DELETE], 0)
        self.assertEqual(len(summary), len(ActivityLog.ACTION_CHOICES))

    def test_sorting_by_a_whitelisted_column(self):
        self.login(self.admin)
        response = self.client.get(self.url, {"sort": "action"})
        actions = [log.action for log in response.context["logs"]]
        self.assertEqual(actions, sorted(actions))

    def test_unknown_sort_value_falls_back_to_newest_first(self):
        self.login(self.admin)
        response = self.client.get(self.url, {"sort": "object_id"})
        self.assertEqual(response.status_code, 200)
        # The LOGIN entry written by signing in is the newest overall.
        self.assertEqual(list(response.context["logs"])[0].action, ActivityLog.LOGIN)

    def test_the_subtitle_counts_the_entries_on_screen(self):
        self.login(self.admin)
        response = self.client.get(self.url, {"action": "create"})
        self.assertEqual(
            response.context["page_subtitle"], "1 audit entry in this view, newest first"
        )

    def test_a_filtered_view_with_no_matches_renders_an_empty_state(self):
        self.login(self.admin)
        response = self.client.get(self.url, {"q": "nothing-like-this"})
        self.assertContains(response, "No entries match this view")
        self.assertEqual(
            response.context["page_subtitle"], "No audit entries match the current view"
        )

    def test_the_trail_is_paginated(self):
        for index in range(15):
            ActivityLog.objects.create(
                user=self.admin, action=ActivityLog.UPDATE, description=f"Entry {index}"
            )
        self.login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["logs"]), 10)
        self.assertTrue(response.context["page_obj"].has_next())


class ActivityLogRoleTests(RailCoreTestCase):
    def test_a_second_administrator_also_reads_the_trail(self):
        spare = create_user("spare_admin", role_name=Role.ADMIN)
        self.assertAllowed(reverse("activity_logs:list"), spare)

    def test_the_module_is_read_only_for_everybody(self):
        from accounts.permissions import MODULE_PERMISSIONS

        self.assertEqual(MODULE_PERMISSIONS["activity_logs"]["manage"], frozenset())
