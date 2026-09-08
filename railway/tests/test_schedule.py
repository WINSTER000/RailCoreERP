"""Schedule CRUD, timing validation, cancellation and role based access."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.factories import RailCoreTestCase
from activity_logs.models import ActivityLog
from notifications.models import Notification
from railway.factories import (
    create_platform,
    create_schedule,
    create_station,
    create_train,
)
from railway.forms import DATETIME_LOCAL_FORMAT, ScheduleForm
from railway.models import Schedule


def _stamp(value):
    """Render a datetime the way ``<input type="datetime-local">`` posts it."""
    return timezone.localtime(value).strftime(DATETIME_LOCAL_FORMAT)


class ScheduleModelTests(RailCoreTestCase):
    def test_display_status_reports_scheduled_by_default(self):
        schedule = create_schedule()
        self.assertEqual(schedule.display_status, Schedule.SCHEDULED)

    def test_display_status_reports_a_delay(self):
        schedule = create_schedule(delay_minutes=25)
        self.assertEqual(schedule.display_status, Schedule.DELAYED)

    def test_display_status_reports_a_cancellation_over_a_delay(self):
        schedule = create_schedule(delay_minutes=25, is_cancelled=True)
        self.assertEqual(schedule.display_status, Schedule.CANCELLED)

    def test_display_status_reports_a_past_run_as_completed(self):
        departure = timezone.now() - timedelta(hours=10)
        schedule = create_schedule(
            departure=departure, arrival=departure + timedelta(hours=2)
        )
        self.assertEqual(schedule.display_status, Schedule.COMPLETED)

    def test_expected_arrival_adds_the_delay(self):
        schedule = create_schedule(delay_minutes=30)
        self.assertEqual(
            schedule.expected_arrival, schedule.arrival_datetime + timedelta(minutes=30)
        )

    def test_duration_helpers(self):
        departure = timezone.now() + timedelta(hours=1)
        schedule = create_schedule(
            departure=departure, arrival=departure + timedelta(hours=5, minutes=30)
        )
        self.assertEqual(schedule.duration_minutes, 330)
        self.assertEqual(schedule.duration_display, "5h 30m")

    def test_journey_label_uses_the_route_endpoints(self):
        train = create_train()
        train.route.source_station.station_code = "NDLS"
        train.route.source_station.save()
        train.route.destination_station.station_code = "BCT"
        train.route.destination_station.save()

        schedule = create_schedule(train=train)
        self.assertEqual(schedule.journey_label, "NDLS → BCT")

    def test_arrival_must_be_after_departure(self):
        departure = timezone.now() + timedelta(hours=2)
        schedule = Schedule(
            train=create_train(),
            platform=create_platform(),
            departure_datetime=departure,
            arrival_datetime=departure - timedelta(hours=1),
        )
        with self.assertRaises(ValidationError) as caught:
            schedule.full_clean()
        self.assertIn("arrival_datetime", caught.exception.error_dict)

    def test_platform_cannot_hold_two_overlapping_runs(self):
        platform = create_platform()
        existing = create_schedule(platform=platform)

        clash = Schedule(
            train=create_train(),
            platform=platform,
            departure_datetime=existing.departure_datetime + timedelta(hours=1),
            arrival_datetime=existing.arrival_datetime + timedelta(hours=1),
        )
        with self.assertRaises(ValidationError) as caught:
            clash.full_clean()
        self.assertIn("platform", caught.exception.error_dict)

    def test_a_cancelled_run_releases_its_platform(self):
        platform = create_platform()
        existing = create_schedule(platform=platform, is_cancelled=True)

        replacement = Schedule(
            train=create_train(),
            platform=platform,
            departure_datetime=existing.departure_datetime,
            arrival_datetime=existing.arrival_datetime,
        )
        replacement.full_clean()  # must not raise

    def test_back_to_back_runs_on_one_platform_are_allowed(self):
        platform = create_platform()
        existing = create_schedule(platform=platform)

        following = Schedule(
            train=create_train(),
            platform=platform,
            departure_datetime=existing.arrival_datetime,
            arrival_datetime=existing.arrival_datetime + timedelta(hours=2),
        )
        following.full_clean()  # must not raise


class ScheduleFormTests(RailCoreTestCase):
    def setUp(self):
        self.train = create_train(train_number="12951")
        self.platform = create_platform()
        self.departure = timezone.now() + timedelta(days=1)
        self.arrival = self.departure + timedelta(hours=6)

    def _payload(self, **overrides):
        payload = {
            "train": self.train.pk,
            "platform": self.platform.pk,
            "departure_datetime": _stamp(self.departure),
            "arrival_datetime": _stamp(self.arrival),
            "delay_minutes": 0,
            "is_cancelled": False,
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_is_accepted(self):
        form = ScheduleForm(data=self._payload())
        self.assertTrue(form.is_valid(), form.errors)

    def test_arrival_before_departure_is_rejected(self):
        form = ScheduleForm(
            data=self._payload(
                arrival_datetime=_stamp(self.departure - timedelta(hours=1))
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("arrival_datetime", form.errors)

    def test_arrival_equal_to_departure_is_rejected(self):
        form = ScheduleForm(data=self._payload(arrival_datetime=_stamp(self.departure)))
        self.assertFalse(form.is_valid())
        self.assertIn("arrival_datetime", form.errors)

    def test_double_booking_a_platform_is_rejected(self):
        create_schedule(
            platform=self.platform, departure=self.departure, arrival=self.arrival
        )
        form = ScheduleForm(data=self._payload(train=create_train().pk))
        self.assertFalse(form.is_valid())
        self.assertIn("platform", form.errors)

    def test_delay_is_capped_at_one_day(self):
        form = ScheduleForm(data=self._payload(delay_minutes=1441))
        self.assertFalse(form.is_valid())
        self.assertIn("delay_minutes", form.errors)

    def test_a_full_day_delay_is_accepted(self):
        form = ScheduleForm(data=self._payload(delay_minutes=1440))
        self.assertTrue(form.is_valid(), form.errors)

    def test_negative_delay_is_rejected(self):
        form = ScheduleForm(data=self._payload(delay_minutes=-5))
        self.assertFalse(form.is_valid())
        self.assertIn("delay_minutes", form.errors)

    def test_required_fields_are_enforced(self):
        form = ScheduleForm(data={})
        self.assertFalse(form.is_valid())
        for field in ("train", "platform", "departure_datetime", "arrival_datetime"):
            self.assertIn(field, form.errors)

    def test_archived_trains_are_not_selectable(self):
        archived = create_train(train_number="19019")
        archived.soft_delete()
        form = ScheduleForm()
        self.assertNotIn(archived, form.fields["train"].queryset)

    def test_editing_keeps_an_archived_train_selectable(self):
        schedule = create_schedule(train=self.train)
        self.train.soft_delete()
        form = ScheduleForm(instance=schedule)
        self.assertIn(self.train, form.fields["train"].queryset)

    def test_closed_platforms_are_not_selectable(self):
        closed = create_platform(is_active=False)
        form = ScheduleForm()
        self.assertNotIn(closed, form.fields["platform"].queryset)

    def test_platform_options_are_grouped_by_station(self):
        first = create_station(station_code="AAA")
        second = create_station(station_code="BBB")
        create_platform(station=first, platform_number=1)
        create_platform(station=second, platform_number=1)

        groups = [label for label, _ in ScheduleForm().fields["platform"].choices if label]
        self.assertIn("AAA - " + first.name, groups)
        self.assertIn("BBB - " + second.name, groups)


class ScheduleViewTests(RailCoreTestCase):
    def setUp(self):
        self.train = create_train(train_number="12951", train_name="Mumbai Rajdhani")
        self.platform = create_platform()
        self.schedule = create_schedule(train=self.train, platform=self.platform)
        self.list_url = reverse("railway:schedule_list")
        self.add_url = reverse("railway:schedule_add")
        self.detail_url = reverse("railway:schedule_detail", args=[self.schedule.pk])
        self.edit_url = reverse("railway:schedule_edit", args=[self.schedule.pk])
        self.delete_url = reverse("railway:schedule_delete", args=[self.schedule.pk])
        self.cancel_url = reverse("railway:schedule_cancel", args=[self.schedule.pk])

    def _payload(self, **overrides):
        payload = {
            "train": self.train.pk,
            "platform": self.platform.pk,
            "departure_datetime": _stamp(self.schedule.departure_datetime),
            "arrival_datetime": _stamp(self.schedule.arrival_datetime),
            "delay_minutes": 0,
            "is_cancelled": False,
        }
        payload.update(overrides)
        return payload

    # -- read access ---------------------------------------------------
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_every_role_can_read_the_timetable(self):
        for user in (
            self.admin,
            self.railway_manager,
            self.station_manager,
            self.operations_staff,
        ):
            with self.subTest(role=user.role_name):
                self.assertAllowed(self.list_url, user)

    def test_detail_shows_the_run_and_its_halts(self):
        self.login(self.station_manager)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mumbai Rajdhani")

    # -- write access --------------------------------------------------
    def test_operations_staff_can_book_a_run(self):
        self.login(self.operations_staff)
        departure = timezone.now() + timedelta(days=4)
        response = self.client.post(
            self.add_url,
            self._payload(
                platform=create_platform().pk,
                departure_datetime=_stamp(departure),
                arrival_datetime=_stamp(departure + timedelta(hours=5)),
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Schedule.objects.count(), 2)

    def test_booking_a_run_writes_an_activity_log_entry(self):
        self.login(self.operations_staff)
        departure = timezone.now() + timedelta(days=4)
        self.client.post(
            self.add_url,
            self._payload(
                platform=create_platform().pk,
                departure_datetime=_stamp(departure),
                arrival_datetime=_stamp(departure + timedelta(hours=5)),
            ),
        )
        self.assertTrue(
            ActivityLog.objects.filter(
                action=ActivityLog.CREATE, model_name="Schedule"
            ).exists()
        )

    def test_station_manager_cannot_book_a_run(self):
        self.assertForbidden(self.add_url, self.station_manager)

    def test_station_manager_cannot_edit_a_run(self):
        self.assertForbidden(self.edit_url, self.station_manager)

    def test_station_manager_cannot_delete_a_run(self):
        self.assertForbidden(self.delete_url, self.station_manager)

    def test_add_form_prefills_the_train_from_the_query_string(self):
        self.login(self.operations_staff)
        response = self.client.get(self.add_url, {"train": self.train.pk})
        self.assertEqual(response.context["form"].initial["train"], self.train.pk)

    def test_invalid_timings_redisplay_the_form(self):
        self.login(self.operations_staff)
        response = self.client.post(
            self.edit_url,
            self._payload(
                arrival_datetime=_stamp(
                    self.schedule.departure_datetime - timedelta(hours=2)
                )
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("arrival_datetime", response.context["form"].errors)

    def test_recording_a_delay_notifies_every_operating_role(self):
        self.login(self.operations_staff)
        response = self.client.post(self.edit_url, self._payload(delay_minutes=45))
        self.assertEqual(response.status_code, 302)

        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.delay_minutes, 45)
        self.assertTrue(
            Notification.objects.filter(
                title__icontains="delayed 45 minutes", level=Notification.WARNING
            ).exists()
        )

    def test_an_unchanged_delay_raises_no_new_notification(self):
        self.login(self.operations_staff)
        self.client.post(self.edit_url, self._payload(delay_minutes=0))
        self.assertFalse(
            Notification.objects.filter(title__icontains="delayed").exists()
        )

    # -- cancellation --------------------------------------------------
    def test_cancelling_needs_a_post(self):
        self.login(self.operations_staff)
        response = self.client.get(self.cancel_url)
        self.assertEqual(response.status_code, 405)

    def test_cancelling_a_run_flags_it_and_notifies_everyone(self):
        self.login(self.operations_staff)
        response = self.client.post(self.cancel_url)
        self.assertEqual(response.status_code, 302)

        self.schedule.refresh_from_db()
        self.assertTrue(self.schedule.is_cancelled)
        self.assertEqual(self.schedule.display_status, Schedule.CANCELLED)
        self.assertTrue(
            Notification.objects.filter(
                title__icontains="cancelled", level=Notification.DANGER
            ).exists()
        )

    def test_cancelling_keeps_the_record_for_reporting(self):
        self.login(self.operations_staff)
        self.client.post(self.cancel_url)
        self.assertTrue(Schedule.objects.filter(pk=self.schedule.pk).exists())

    def test_a_cancelled_run_can_be_reinstated(self):
        self.schedule.is_cancelled = True
        self.schedule.save(update_fields=["is_cancelled"])

        self.login(self.operations_staff)
        self.client.post(self.cancel_url)

        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_cancelled)
        self.assertTrue(
            Notification.objects.filter(
                title__icontains="reinstated", level=Notification.SUCCESS
            ).exists()
        )

    def test_reinstating_is_refused_when_the_platform_was_taken(self):
        self.schedule.is_cancelled = True
        self.schedule.save(update_fields=["is_cancelled"])
        create_schedule(
            train=create_train(),
            platform=self.platform,
            departure=self.schedule.departure_datetime,
            arrival=self.schedule.arrival_datetime,
        )

        self.login(self.operations_staff)
        self.client.post(self.cancel_url)

        self.schedule.refresh_from_db()
        self.assertTrue(self.schedule.is_cancelled)

    def test_station_manager_cannot_cancel_a_run(self):
        self.assertForbidden(self.cancel_url, self.station_manager, method="post")

    # -- delete --------------------------------------------------------
    def test_delete_shows_a_confirmation_before_acting(self):
        self.login(self.operations_staff)
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Schedule.objects.filter(pk=self.schedule.pk).exists())

    def test_post_deletes_the_run(self):
        self.login(self.operations_staff)
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Schedule.objects.filter(pk=self.schedule.pk).exists())

    # -- list behaviour ------------------------------------------------
    def test_cancelled_filter_narrows_the_list(self):
        create_schedule(platform=create_platform(), is_cancelled=True)
        self.login(self.admin)
        response = self.client.get(self.list_url, {"status": "cancelled"})
        self.assertTrue(all(s.is_cancelled for s in response.context["schedules"]))

    def test_delayed_filter_narrows_the_list(self):
        create_schedule(platform=create_platform(), delay_minutes=15)
        self.login(self.admin)
        response = self.client.get(self.list_url, {"status": "delayed"})
        self.assertTrue(all(s.delay_minutes for s in response.context["schedules"]))

    def test_completed_filter_shows_only_past_runs(self):
        departure = timezone.now() - timedelta(days=1)
        create_schedule(
            platform=create_platform(),
            departure=departure,
            arrival=departure + timedelta(hours=2),
        )
        self.login(self.admin)
        response = self.client.get(self.list_url, {"status": "completed"})
        now = timezone.now()
        self.assertTrue(
            all(s.arrival_datetime < now for s in response.context["schedules"])
        )

    def test_train_filter_narrows_the_list(self):
        create_schedule(train=create_train(), platform=create_platform())
        self.login(self.admin)
        response = self.client.get(self.list_url, {"train": self.train.pk})
        trains = {s.train_id for s in response.context["schedules"]}
        self.assertEqual(trains, {self.train.pk})

    def test_search_matches_the_train_number(self):
        create_schedule(train=create_train(train_number="12002"), platform=create_platform())
        self.login(self.admin)
        response = self.client.get(self.list_url, {"q": "12951"})
        trains = {s.train_id for s in response.context["schedules"]}
        self.assertEqual(trains, {self.train.pk})

    def test_counts_come_from_the_filtered_queryset(self):
        create_schedule(platform=create_platform(), delay_minutes=20)
        create_schedule(platform=create_platform(), is_cancelled=True)
        self.login(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.context["total_count"], 3)
        self.assertEqual(response.context["delayed_count"], 1)
        self.assertEqual(response.context["cancelled_count"], 1)

    def test_unknown_sort_value_falls_back_to_the_default(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"sort": "train__secret"})
        self.assertEqual(response.status_code, 200)

    def test_empty_list_renders_an_empty_state(self):
        Schedule.objects.all().delete()
        self.login(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The timetable is empty")
