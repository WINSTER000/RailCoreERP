"""Train CRUD, number uniqueness, soft delete and role based access."""

from django.urls import reverse

from accounts.factories import RailCoreTestCase
from activity_logs.models import ActivityLog
from notifications.models import Notification
from railway.factories import create_route, create_schedule, create_train
from railway.forms import TrainForm
from railway.models import Train


class TrainModelTests(RailCoreTestCase):
    def test_string_shows_number_and_name(self):
        train = create_train(train_number="12951", train_name="Mumbai Rajdhani")
        self.assertEqual(str(train), "12951 - Mumbai Rajdhani")

    def test_soft_delete_hides_the_train_from_the_default_manager(self):
        train = create_train()
        train.soft_delete()

        self.assertFalse(Train.objects.filter(pk=train.pk).exists())
        self.assertTrue(Train.all_objects.filter(pk=train.pk).exists())
        self.assertTrue(Train.all_objects.deleted().filter(pk=train.pk).exists())

    def test_restore_brings_the_train_back(self):
        train = create_train()
        train.soft_delete()
        train.restore()

        self.assertTrue(Train.objects.filter(pk=train.pk).exists())
        self.assertEqual(Train.all_objects.deleted().count(), 0)

    def test_status_queryset_helpers(self):
        create_train(status=Train.ACTIVE)
        create_train(status=Train.MAINTENANCE)
        create_train(status=Train.INACTIVE)

        self.assertEqual(Train.objects.active().count(), 1)
        self.assertEqual(Train.objects.maintenance().count(), 1)
        self.assertEqual(Train.objects.count(), 3)

    def test_schedule_counts(self):
        train = create_train()
        self.assertEqual(train.schedule_count, 0)
        self.assertEqual(train.upcoming_schedule_count, 0)

        create_schedule(train=train)
        self.assertEqual(train.schedule_count, 1)
        self.assertEqual(train.upcoming_schedule_count, 1)

    def test_cancelled_runs_are_not_counted_as_upcoming(self):
        train = create_train()
        create_schedule(train=train, is_cancelled=True)
        self.assertEqual(train.schedule_count, 1)
        self.assertEqual(train.upcoming_schedule_count, 0)


class TrainFormTests(RailCoreTestCase):
    def setUp(self):
        self.route = create_route(route_name="Delhi - Mumbai Central")

    def _payload(self, **overrides):
        payload = {
            "train_number": "12951",
            "train_name": "Mumbai Rajdhani Express",
            "route": self.route.pk,
            "total_coaches": 18,
            "status": Train.ACTIVE,
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_is_accepted(self):
        self.assertTrue(TrainForm(data=self._payload()).is_valid())

    def test_duplicate_train_number_is_rejected(self):
        create_train(train_number="12951", train_name="Existing Express")
        form = TrainForm(data=self._payload())
        self.assertFalse(form.is_valid())
        self.assertIn("train_number", form.errors)
        self.assertIn("Existing Express", form.errors["train_number"][0])

    def test_number_held_by_an_archived_train_reports_the_archive(self):
        archived = create_train(train_number="12951", train_name="Archived Express")
        archived.soft_delete()

        form = TrainForm(data=self._payload())
        self.assertFalse(form.is_valid())
        self.assertIn("archived", form.errors["train_number"][0].lower())

    def test_train_number_must_be_four_to_six_digits(self):
        for number in ("123", "1234567", "12A51", ""):
            with self.subTest(number=number):
                form = TrainForm(data=self._payload(train_number=number))
                self.assertFalse(form.is_valid())
                self.assertIn("train_number", form.errors)

    def test_coach_count_must_stay_between_one_and_thirty(self):
        for coaches in (0, 31):
            with self.subTest(coaches=coaches):
                form = TrainForm(data=self._payload(total_coaches=coaches))
                self.assertFalse(form.is_valid())
                self.assertIn("total_coaches", form.errors)

    def test_a_single_coach_rake_is_accepted(self):
        self.assertTrue(TrainForm(data=self._payload(total_coaches=1)).is_valid())

    def test_status_must_be_one_of_the_choices(self):
        form = TrainForm(data=self._payload(status="RETIRED"))
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_editing_a_train_keeps_its_own_number(self):
        train = create_train(train_number="12951")
        form = TrainForm(data=self._payload(), instance=train)
        self.assertTrue(form.is_valid(), form.errors)

    def test_required_fields_are_enforced(self):
        form = TrainForm(data={})
        self.assertFalse(form.is_valid())
        for field in ("train_number", "train_name", "route"):
            self.assertIn(field, form.errors)

    def test_withdrawn_routes_are_not_selectable(self):
        withdrawn = create_route(route_name="Withdrawn Corridor", is_active=False)
        form = TrainForm()
        self.assertNotIn(withdrawn, form.fields["route"].queryset)

    def test_editing_keeps_a_withdrawn_route_selectable(self):
        withdrawn = create_route(route_name="Withdrawn Corridor 2", is_active=False)
        train = create_train(route=withdrawn)
        form = TrainForm(instance=train)
        self.assertIn(withdrawn, form.fields["route"].queryset)


class TrainViewTests(RailCoreTestCase):
    def setUp(self):
        self.route = create_route(route_name="Delhi - Mumbai Central")
        self.train = create_train(
            train_number="12951", train_name="Mumbai Rajdhani", route=self.route
        )
        self.list_url = reverse("railway:train_list")
        self.add_url = reverse("railway:train_add")
        self.archive_url = reverse("railway:train_archive")
        self.detail_url = reverse("railway:train_detail", args=[self.train.pk])
        self.edit_url = reverse("railway:train_edit", args=[self.train.pk])
        self.delete_url = reverse("railway:train_delete", args=[self.train.pk])
        self.restore_url = reverse("railway:train_restore", args=[self.train.pk])

    def _payload(self, **overrides):
        payload = {
            "train_number": self.train.train_number,
            "train_name": self.train.train_name,
            "route": self.route.pk,
            "total_coaches": 18,
            "status": Train.ACTIVE,
        }
        payload.update(overrides)
        return payload

    # -- read access ---------------------------------------------------
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_admin_railway_manager_and_operations_staff_can_read_trains(self):
        for user in (self.admin, self.railway_manager, self.operations_staff):
            with self.subTest(role=user.role_name):
                self.assertAllowed(self.list_url, user)

    def test_station_manager_cannot_read_the_train_list(self):
        self.assertForbidden(self.list_url, self.station_manager)

    def test_detail_shows_the_route_halts_and_runs(self):
        create_schedule(train=self.train)
        self.login(self.railway_manager)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["schedule_count"], 1)
        self.assertContains(response, "Mumbai Rajdhani")

    # -- write access --------------------------------------------------
    def test_railway_manager_can_register_a_train(self):
        self.login(self.railway_manager)
        response = self.client.post(
            self.add_url, self._payload(train_number="12952", train_name="Delhi Rajdhani")
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Train.objects.filter(train_number="12952").exists())

    def test_creating_a_train_logs_the_activity_and_notifies_operations(self):
        self.login(self.railway_manager)
        self.client.post(
            self.add_url, self._payload(train_number="12952", train_name="Delhi Rajdhani")
        )
        self.assertTrue(
            ActivityLog.objects.filter(
                action=ActivityLog.CREATE, model_name="Train"
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(title="New train added")
            .exclude(user=self.railway_manager)
            .exists()
        )

    def test_the_author_of_a_change_is_not_notified_about_it(self):
        self.login(self.railway_manager)
        self.client.post(
            self.add_url, self._payload(train_number="12952", train_name="Delhi Rajdhani")
        )
        self.assertFalse(
            Notification.objects.filter(
                user=self.railway_manager, title="New train added"
            ).exists()
        )

    def test_station_manager_cannot_register_a_train(self):
        self.assertForbidden(self.add_url, self.station_manager)

    def test_operations_staff_cannot_edit_a_train(self):
        self.assertForbidden(self.edit_url, self.operations_staff)

    def test_operations_staff_cannot_archive_a_train(self):
        self.assertForbidden(self.delete_url, self.operations_staff)

    def test_admin_can_edit_a_train(self):
        self.login(self.admin)
        response = self.client.post(self.edit_url, self._payload(total_coaches=22))
        self.assertEqual(response.status_code, 302)
        self.train.refresh_from_db()
        self.assertEqual(self.train.total_coaches, 22)

    def test_a_status_change_raises_a_notification(self):
        self.login(self.railway_manager)
        self.client.post(self.edit_url, self._payload(status=Train.MAINTENANCE))
        self.train.refresh_from_db()
        self.assertEqual(self.train.status, Train.MAINTENANCE)
        self.assertTrue(
            Notification.objects.filter(
                title__icontains="is now maintenance", level=Notification.WARNING
            ).exists()
        )

    def test_editing_without_a_status_change_raises_no_notification(self):
        self.login(self.railway_manager)
        self.client.post(self.edit_url, self._payload(total_coaches=20))
        self.assertFalse(
            Notification.objects.filter(title__icontains="is now").exists()
        )

    def test_duplicate_number_redisplays_the_form_with_an_error(self):
        create_train(train_number="12999", train_name="Other Express")
        self.login(self.railway_manager)
        response = self.client.post(self.edit_url, self._payload(train_number="12999"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("train_number", response.context["form"].errors)

    # -- soft delete, archive and restore ------------------------------
    def test_delete_shows_a_confirmation_before_archiving(self):
        self.login(self.railway_manager)
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Train.objects.filter(pk=self.train.pk).exists())
        self.assertTrue(response.context["soft_delete"])

    def test_post_archives_the_train_instead_of_deleting_the_row(self):
        self.login(self.railway_manager)
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 302)

        self.train.refresh_from_db()
        self.assertTrue(self.train.is_deleted)
        self.assertFalse(Train.objects.filter(pk=self.train.pk).exists())
        self.assertTrue(Train.all_objects.filter(pk=self.train.pk).exists())

    def test_archiving_keeps_the_recorded_schedules(self):
        schedule = create_schedule(train=self.train)
        self.login(self.railway_manager)
        self.client.post(self.delete_url)
        self.assertTrue(
            self.train.schedules.model.objects.filter(pk=schedule.pk).exists()
        )

    def test_archived_train_is_absent_from_the_list_and_present_in_the_archive(self):
        self.train.soft_delete()
        self.login(self.railway_manager)

        listed = self.client.get(self.list_url)
        self.assertNotIn(self.train, list(listed.context["trains"]))
        self.assertEqual(listed.context["archived_count"], 1)

        archived = self.client.get(self.archive_url)
        self.assertIn(self.train, list(archived.context["trains"]))

    def test_restore_needs_a_post(self):
        self.train.soft_delete()
        self.login(self.railway_manager)
        response = self.client.get(self.restore_url)
        self.assertEqual(response.status_code, 405)

    def test_railway_manager_can_restore_an_archived_train(self):
        self.train.soft_delete()
        self.login(self.railway_manager)
        response = self.client.post(self.restore_url)
        self.assertEqual(response.status_code, 302)

        self.train.refresh_from_db()
        self.assertFalse(self.train.is_deleted)

    def test_operations_staff_cannot_restore_a_train(self):
        self.train.soft_delete()
        self.assertForbidden(self.restore_url, self.operations_staff, method="post")

    def test_restoring_a_live_train_is_a_harmless_no_op(self):
        self.login(self.railway_manager)
        response = self.client.post(self.restore_url)
        self.assertEqual(response.status_code, 302)
        self.train.refresh_from_db()
        self.assertFalse(self.train.is_deleted)

    def test_archive_shows_the_restore_button_only_to_managers(self):
        self.train.soft_delete()

        self.login(self.railway_manager)
        self.assertTrue(self.client.get(self.archive_url).context["can_restore"])

        self.login(self.operations_staff)
        self.assertFalse(self.client.get(self.archive_url).context["can_restore"])

    # -- list behaviour ------------------------------------------------
    def test_search_narrows_the_list(self):
        create_train(train_number="12002", train_name="Shatabdi Express")
        self.login(self.admin)
        response = self.client.get(self.list_url, {"q": "Shatabdi"})
        names = [t.train_name for t in response.context["trains"]]
        self.assertEqual(names, ["Shatabdi Express"])

    def test_status_filter_narrows_the_list(self):
        create_train(train_number="12003", status=Train.MAINTENANCE)
        self.login(self.admin)
        response = self.client.get(self.list_url, {"status": Train.MAINTENANCE})
        statuses = {t.status for t in response.context["trains"]}
        self.assertEqual(statuses, {Train.MAINTENANCE})

    def test_route_filter_narrows_the_list(self):
        other = create_route(route_name="Chennai - Bengaluru")
        create_train(train_number="12004", route=other)
        self.login(self.admin)
        response = self.client.get(self.list_url, {"route": self.route.pk})
        routes = {t.route_id for t in response.context["trains"]}
        self.assertEqual(routes, {self.route.pk})

    def test_coach_total_is_summed_from_the_database(self):
        create_train(train_number="12005", total_coaches=12)
        self.login(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.context["coach_total"], 18 + 12)

    def test_unknown_sort_value_falls_back_to_the_default(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"sort": "is_deleted"})
        self.assertEqual(response.status_code, 200)

    def test_empty_list_renders_an_empty_state(self):
        Train.all_objects.all().delete()
        self.login(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No trains registered yet")

    def test_empty_archive_renders_an_empty_state(self):
        self.login(self.admin)
        response = self.client.get(self.archive_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing in the archive")
