"""Platform CRUD, per-station uniqueness and role based access."""

from django.urls import reverse

from accounts.factories import RailCoreTestCase
from railway.factories import create_platform, create_schedule, create_station
from railway.forms import PlatformForm
from railway.models import Platform


class PlatformModelTests(RailCoreTestCase):
    def test_string_and_label_read_naturally(self):
        station = create_station(station_code="NDLS")
        platform = create_platform(station=station, platform_number=3)

        self.assertEqual(str(platform), "NDLS - Platform 3")
        self.assertEqual(platform.label, "Platform 3")

    def test_status_label_tracks_is_active(self):
        self.assertEqual(create_platform().status_label, "ACTIVE")
        self.assertEqual(create_platform(is_active=False).status_label, "INACTIVE")

    def test_schedule_count_counts_bookings(self):
        platform = create_platform()
        self.assertEqual(platform.schedule_count, 0)
        create_schedule(platform=platform)
        self.assertEqual(platform.schedule_count, 1)

    def test_same_number_is_allowed_at_a_different_station(self):
        create_platform(station=create_station(), platform_number=1)
        create_platform(station=create_station(), platform_number=1)
        self.assertEqual(Platform.objects.filter(platform_number=1).count(), 2)


class PlatformFormTests(RailCoreTestCase):
    def setUp(self):
        self.station = create_station(station_code="NDLS")

    def _payload(self, **overrides):
        payload = {
            "station": self.station.pk,
            "platform_number": 1,
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_is_accepted(self):
        self.assertTrue(PlatformForm(data=self._payload()).is_valid())

    def test_duplicate_number_at_the_same_station_is_rejected(self):
        create_platform(station=self.station, platform_number=1)
        form = PlatformForm(data=self._payload())
        self.assertFalse(form.is_valid())
        self.assertIn("platform_number", form.errors)

    def test_duplicate_error_names_the_station(self):
        create_platform(station=self.station, platform_number=4)
        form = PlatformForm(data=self._payload(platform_number=4))
        self.assertFalse(form.is_valid())
        self.assertIn("NDLS already has a platform 4", form.errors["platform_number"][0])

    def test_editing_a_platform_does_not_clash_with_itself(self):
        platform = create_platform(station=self.station, platform_number=2)
        form = PlatformForm(data=self._payload(platform_number=2), instance=platform)
        self.assertTrue(form.is_valid(), form.errors)

    def test_platform_number_must_be_within_range(self):
        for number in (0, 100):
            with self.subTest(number=number):
                form = PlatformForm(data=self._payload(platform_number=number))
                self.assertFalse(form.is_valid())
                self.assertIn("platform_number", form.errors)

    def test_station_is_required(self):
        form = PlatformForm(data=self._payload(station=""))
        self.assertFalse(form.is_valid())
        self.assertIn("station", form.errors)

    def test_inactive_stations_are_not_selectable(self):
        retired = create_station(station_code="OLDX", is_active=False)
        form = PlatformForm()
        self.assertNotIn(retired, form.fields["station"].queryset)

    def test_editing_keeps_a_retired_station_selectable(self):
        retired = create_station(station_code="OLDY", is_active=False)
        platform = create_platform(station=retired, platform_number=1)
        form = PlatformForm(instance=platform)
        self.assertIn(retired, form.fields["station"].queryset)


class PlatformViewTests(RailCoreTestCase):
    def setUp(self):
        self.station = create_station(name="Howrah", station_code="HWH")
        self.platform = create_platform(station=self.station, platform_number=1)
        self.list_url = reverse("railway:platform_list")
        self.add_url = reverse("railway:platform_add")
        self.edit_url = reverse("railway:platform_edit", args=[self.platform.pk])
        self.delete_url = reverse("railway:platform_delete", args=[self.platform.pk])

    def _payload(self, **overrides):
        payload = {
            "station": self.station.pk,
            "platform_number": self.platform.platform_number,
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    # -- read access ---------------------------------------------------
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_every_role_can_read_the_platform_list(self):
        for user in (
            self.admin,
            self.railway_manager,
            self.station_manager,
            self.operations_staff,
        ):
            with self.subTest(role=user.role_name):
                self.assertAllowed(self.list_url, user)

    # -- write access --------------------------------------------------
    def test_station_manager_can_add_a_platform(self):
        self.login(self.station_manager)
        response = self.client.post(self.add_url, self._payload(platform_number=2))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Platform.objects.filter(station=self.station, platform_number=2).exists()
        )

    def test_railway_manager_cannot_add_a_platform(self):
        self.assertForbidden(self.add_url, self.railway_manager)

    def test_operations_staff_cannot_edit_a_platform(self):
        self.assertForbidden(self.edit_url, self.operations_staff)

    def test_operations_staff_cannot_delete_a_platform(self):
        self.assertForbidden(self.delete_url, self.operations_staff)

    def test_admin_can_close_a_platform_for_maintenance(self):
        self.login(self.admin)
        response = self.client.post(self.edit_url, self._payload(is_active=False))
        self.assertEqual(response.status_code, 302)
        self.platform.refresh_from_db()
        self.assertFalse(self.platform.is_active)

    def test_duplicate_number_redisplays_the_form_with_an_error(self):
        create_platform(station=self.station, platform_number=5)
        self.login(self.station_manager)
        response = self.client.post(self.add_url, self._payload(platform_number=5))
        self.assertEqual(response.status_code, 200)
        self.assertIn("platform_number", response.context["form"].errors)

    def test_add_form_prefills_the_station_from_the_query_string(self):
        self.login(self.station_manager)
        response = self.client.get(self.add_url, {"station": self.station.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["station"], self.station.pk)

    def test_a_bogus_station_query_value_is_ignored(self):
        self.login(self.station_manager)
        response = self.client.get(self.add_url, {"station": "drop-table"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("station", response.context["form"].initial)

    # -- delete --------------------------------------------------------
    def test_delete_shows_a_confirmation_before_acting(self):
        self.login(self.station_manager)
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Platform.objects.filter(pk=self.platform.pk).exists())

    def test_post_deletes_the_platform(self):
        self.login(self.station_manager)
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Platform.objects.filter(pk=self.platform.pk).exists())

    def test_platform_holding_a_schedule_is_protected_from_deletion(self):
        create_schedule(platform=self.platform)
        self.login(self.station_manager)
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Platform.objects.filter(pk=self.platform.pk).exists())

    # -- list behaviour ------------------------------------------------
    def test_station_filter_narrows_the_list(self):
        other = create_station(name="Sealdah", station_code="SDAH")
        create_platform(station=other, platform_number=1)
        self.login(self.admin)
        response = self.client.get(self.list_url, {"station": self.station.pk})
        stations = {p.station_id for p in response.context["platforms"]}
        self.assertEqual(stations, {self.station.pk})

    def test_status_filter_hides_closed_platforms(self):
        create_platform(station=self.station, platform_number=9, is_active=False)
        self.login(self.admin)
        response = self.client.get(self.list_url, {"status": "active"})
        numbers = [p.platform_number for p in response.context["platforms"]]
        self.assertNotIn(9, numbers)

    def test_search_matches_the_station_name(self):
        other = create_station(name="Sealdah", station_code="SDAH")
        create_platform(station=other, platform_number=1)
        self.login(self.admin)
        response = self.client.get(self.list_url, {"q": "Sealdah"})
        stations = {p.station_id for p in response.context["platforms"]}
        self.assertEqual(stations, {other.pk})

    def test_unknown_sort_value_falls_back_to_the_default(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"sort": "station__password"})
        self.assertEqual(response.status_code, 200)

    def test_empty_list_renders_an_empty_state(self):
        Platform.objects.all().delete()
        self.login(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No platforms yet")
