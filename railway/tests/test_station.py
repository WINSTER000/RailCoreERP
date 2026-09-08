"""Station CRUD, validation and role based access."""

from django.urls import reverse

from accounts.factories import RailCoreTestCase
from activity_logs.models import ActivityLog
from railway.factories import create_platform, create_route, create_station
from railway.forms import StationForm
from railway.models import Station


class StationModelTests(RailCoreTestCase):
    def test_station_code_is_upper_cased_on_save(self):
        station = Station.objects.create(
            name="Test Central", station_code="tcx", city="Testville", state="Testland"
        )
        self.assertEqual(station.station_code, "TCX")

    def test_location_and_platform_counts(self):
        station = create_station(city="Pune", state="Maharashtra")
        create_platform(station=station, platform_number=1)
        create_platform(station=station, platform_number=2, is_active=False)

        self.assertEqual(station.location, "Pune, Maharashtra")
        self.assertEqual(station.platform_count, 2)
        self.assertEqual(station.active_platform_count, 1)

    def test_status_label_tracks_is_active(self):
        self.assertEqual(create_station().status_label, "ACTIVE")
        self.assertEqual(create_station(is_active=False).status_label, "INACTIVE")


class StationFormTests(RailCoreTestCase):
    def _payload(self, **overrides):
        payload = {
            "name": "Nagpur Junction",
            "station_code": "NGPX",
            "city": "Nagpur",
            "state": "Maharashtra",
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_is_accepted(self):
        self.assertTrue(StationForm(data=self._payload()).is_valid())

    def test_duplicate_station_code_is_rejected(self):
        create_station(station_code="NGPX")
        form = StationForm(data=self._payload())
        self.assertFalse(form.is_valid())
        self.assertIn("station_code", form.errors)

    def test_duplicate_code_is_caught_case_insensitively(self):
        create_station(station_code="NGPX")
        form = StationForm(data=self._payload(station_code="ngpx"))
        self.assertFalse(form.is_valid())
        self.assertIn("station_code", form.errors)

    def test_invalid_station_code_characters_are_rejected(self):
        form = StationForm(data=self._payload(station_code="N-G P"))
        self.assertFalse(form.is_valid())
        self.assertIn("station_code", form.errors)

    def test_required_fields_are_enforced(self):
        form = StationForm(data={})
        self.assertFalse(form.is_valid())
        for field in ("name", "station_code", "city", "state"):
            self.assertIn(field, form.errors)


class StationViewTests(RailCoreTestCase):
    def setUp(self):
        self.station = create_station(name="Kanpur Central", station_code="CNBX")
        self.list_url = reverse("railway:station_list")
        self.add_url = reverse("railway:station_add")
        self.detail_url = reverse("railway:station_detail", args=[self.station.pk])
        self.edit_url = reverse("railway:station_edit", args=[self.station.pk])
        self.delete_url = reverse("railway:station_delete", args=[self.station.pk])

    def _payload(self, **overrides):
        payload = {
            "name": "Kanpur Central",
            "station_code": "CNBX",
            "city": "Kanpur",
            "state": "Uttar Pradesh",
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    # -- read access ---------------------------------------------------
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_every_role_can_read_the_station_list(self):
        for user in (
            self.admin,
            self.railway_manager,
            self.station_manager,
            self.operations_staff,
        ):
            with self.subTest(role=user.role_name):
                self.assertAllowed(self.list_url, user)

    def test_station_detail_lists_platforms_and_departures(self):
        create_platform(station=self.station, platform_number=1)
        self.login(self.station_manager)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["platform_count"], 1)
        self.assertContains(response, "Kanpur Central")

    # -- write access --------------------------------------------------
    def test_station_manager_can_create_a_station(self):
        self.login(self.station_manager)
        response = self.client.post(
            self.add_url, self._payload(name="Surat", station_code="STX")
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Station.objects.filter(station_code="STX").exists())

    def test_creating_a_station_writes_an_activity_log_entry(self):
        self.login(self.station_manager)
        self.client.post(self.add_url, self._payload(name="Surat", station_code="STX"))
        self.assertTrue(
            ActivityLog.objects.filter(
                action=ActivityLog.CREATE, model_name="Station"
            ).exists()
        )

    def test_railway_manager_cannot_create_a_station(self):
        self.assertForbidden(self.add_url, self.railway_manager)

    def test_operations_staff_cannot_edit_a_station(self):
        self.assertForbidden(self.edit_url, self.operations_staff)

    def test_operations_staff_cannot_delete_a_station(self):
        self.assertForbidden(self.delete_url, self.operations_staff)

    def test_admin_can_edit_a_station(self):
        self.login(self.admin)
        response = self.client.post(self.edit_url, self._payload(city="Lucknow"))
        self.assertEqual(response.status_code, 302)
        self.station.refresh_from_db()
        self.assertEqual(self.station.city, "Lucknow")

    def test_invalid_edit_redisplays_the_form_with_errors(self):
        self.login(self.admin)
        response = self.client.post(self.edit_url, self._payload(station_code=""))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)

    # -- delete --------------------------------------------------------
    def test_delete_requires_a_post_and_shows_a_confirmation_first(self):
        self.login(self.station_manager)
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Station.objects.filter(pk=self.station.pk).exists())

    def test_post_deletes_the_station(self):
        self.login(self.station_manager)
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Station.objects.filter(pk=self.station.pk).exists())

    def test_station_used_by_a_route_is_protected_from_deletion(self):
        route = create_route(source_station=self.station)
        self.login(self.station_manager)
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Station.objects.filter(pk=self.station.pk).exists())
        self.assertTrue(route.__class__.objects.filter(pk=route.pk).exists())

    # -- list behaviour ------------------------------------------------
    def test_search_narrows_the_list(self):
        create_station(name="Bhopal Junction", station_code="BPLX")
        self.login(self.admin)
        response = self.client.get(self.list_url, {"q": "Bhopal"})
        names = [s.name for s in response.context["stations"]]
        self.assertEqual(names, ["Bhopal Junction"])

    def test_status_filter_hides_inactive_stations(self):
        create_station(name="Closed Halt", station_code="CLSD", is_active=False)
        self.login(self.admin)
        response = self.client.get(self.list_url, {"status": "active"})
        names = [s.name for s in response.context["stations"]]
        self.assertNotIn("Closed Halt", names)

    def test_unknown_sort_value_falls_back_to_the_default(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"sort": "password"})
        self.assertEqual(response.status_code, 200)

    def test_empty_list_renders_an_empty_state(self):
        Station.objects.all().delete()
        self.login(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No stations")
