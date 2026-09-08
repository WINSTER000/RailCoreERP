"""Route halt CRUD, sequence/station uniqueness and offset validation."""

from django.urls import reverse

from accounts.factories import RailCoreTestCase
from railway.factories import create_route, create_route_station, create_station
from railway.forms import RouteStationForm
from railway.models import RouteStation


class RouteStationModelTests(RailCoreTestCase):
    def test_halt_minutes_is_the_gap_between_the_offsets(self):
        halt = create_route_station(arrival_offset=120, departure_offset=125)
        self.assertEqual(halt.halt_minutes, 5)

    def test_halt_minutes_never_goes_negative(self):
        halt = RouteStation(arrival_offset=120, departure_offset=120)
        self.assertEqual(halt.halt_minutes, 0)

    def test_string_shows_the_route_and_stop_position(self):
        route = create_route(route_name="Delhi - Mumbai Central")
        halt = create_route_station(
            route=route,
            station=create_station(station_code="KTA"),
            sequence_number=3,
        )
        self.assertEqual(str(halt), "Delhi - Mumbai Central · #3 KTA")


class RouteStationFormTests(RailCoreTestCase):
    def setUp(self):
        self.route = create_route(route_name="Delhi - Mumbai Central")
        self.station = create_station(station_code="KTA")

    def _payload(self, **overrides):
        payload = {
            "route": self.route.pk,
            "station": self.station.pk,
            "sequence_number": 2,
            "arrival_offset": 240,
            "departure_offset": 245,
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_is_accepted(self):
        self.assertTrue(RouteStationForm(data=self._payload()).is_valid())

    def test_duplicate_sequence_number_on_the_route_is_rejected(self):
        create_route_station(
            route=self.route, station=create_station(station_code="BPL"), sequence_number=2
        )
        form = RouteStationForm(data=self._payload())
        self.assertFalse(form.is_valid())
        self.assertIn("sequence_number", form.errors)
        self.assertIn("already", form.errors["sequence_number"][0])

    def test_duplicate_station_on_the_route_is_rejected(self):
        create_route_station(route=self.route, station=self.station, sequence_number=5)
        form = RouteStationForm(data=self._payload())
        self.assertFalse(form.is_valid())
        self.assertIn("station", form.errors)

    def test_the_same_station_may_halt_on_a_different_route(self):
        other = create_route(route_name="Delhi - Bhopal")
        create_route_station(route=other, station=self.station, sequence_number=2)
        self.assertTrue(RouteStationForm(data=self._payload()).is_valid())

    def test_departure_offset_cannot_precede_the_arrival_offset(self):
        form = RouteStationForm(
            data=self._payload(arrival_offset=300, departure_offset=240)
        )
        self.assertFalse(form.is_valid())
        self.assertIn("departure_offset", form.errors)

    def test_equal_offsets_are_allowed_for_a_non_stopping_halt(self):
        form = RouteStationForm(
            data=self._payload(arrival_offset=240, departure_offset=240)
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_sequence_number_must_be_at_least_one(self):
        form = RouteStationForm(data=self._payload(sequence_number=0))
        self.assertFalse(form.is_valid())
        self.assertIn("sequence_number", form.errors)

    def test_offsets_are_capped_at_one_week(self):
        form = RouteStationForm(
            data=self._payload(arrival_offset=10081, departure_offset=10081)
        )
        self.assertFalse(form.is_valid())
        self.assertIn("arrival_offset", form.errors)

    def test_editing_a_halt_does_not_clash_with_itself(self):
        halt = create_route_station(
            route=self.route, station=self.station, sequence_number=2
        )
        form = RouteStationForm(data=self._payload(), instance=halt)
        self.assertTrue(form.is_valid(), form.errors)

    def test_required_fields_are_enforced(self):
        form = RouteStationForm(data={})
        self.assertFalse(form.is_valid())
        for field in ("route", "station", "sequence_number"):
            self.assertIn(field, form.errors)


class RouteStationViewTests(RailCoreTestCase):
    def setUp(self):
        self.route = create_route(route_name="Delhi - Mumbai Central")
        self.station = create_station(name="Kota Junction", station_code="KOTA")
        self.halt = create_route_station(
            route=self.route, station=self.station, sequence_number=2
        )
        self.list_url = reverse("railway:route_station_list")
        self.add_url = reverse("railway:route_station_add")
        self.edit_url = reverse("railway:route_station_edit", args=[self.halt.pk])
        self.delete_url = reverse("railway:route_station_delete", args=[self.halt.pk])

    def _payload(self, **overrides):
        payload = {
            "route": self.route.pk,
            "station": self.station.pk,
            "sequence_number": self.halt.sequence_number,
            "arrival_offset": self.halt.arrival_offset,
            "departure_offset": self.halt.departure_offset,
        }
        payload.update(overrides)
        return payload

    # -- read access ---------------------------------------------------
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_every_role_can_read_the_halt_list(self):
        for user in (
            self.admin,
            self.railway_manager,
            self.station_manager,
            self.operations_staff,
        ):
            with self.subTest(role=user.role_name):
                self.assertAllowed(self.list_url, user)

    # -- write access --------------------------------------------------
    def test_station_manager_can_add_a_halt(self):
        other = create_station(station_code="BPL")
        self.login(self.station_manager)
        response = self.client.post(
            self.add_url,
            self._payload(
                station=other.pk,
                sequence_number=3,
                arrival_offset=400,
                departure_offset=405,
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            RouteStation.objects.filter(route=self.route, station=other).exists()
        )

    def _add_a_second_halt(self):
        other = create_station(station_code="BPL")
        return self.client.post(
            self.add_url,
            self._payload(
                station=other.pk,
                sequence_number=3,
                arrival_offset=400,
                departure_offset=405,
            ),
        )

    def test_admin_is_returned_to_the_route_page_after_adding_a_halt(self):
        self.login(self.admin)
        response = self._add_a_second_halt()
        self.assertRedirects(
            response, reverse("railway:route_detail", args=[self.route.pk])
        )

    def test_station_manager_is_returned_to_the_halt_list_they_can_open(self):
        # A Station Manager owns halts but cannot view the routes module, so
        # sending them to route_detail would land them on a 403.
        self.login(self.station_manager)
        response = self._add_a_second_halt()
        self.assertRedirects(
            response, f"{self.list_url}?route={self.route.pk}"
        )

    def test_railway_manager_cannot_add_a_halt(self):
        self.assertForbidden(self.add_url, self.railway_manager)

    def test_operations_staff_cannot_edit_a_halt(self):
        self.assertForbidden(self.edit_url, self.operations_staff)

    def test_operations_staff_cannot_delete_a_halt(self):
        self.assertForbidden(self.delete_url, self.operations_staff)

    def test_admin_can_retime_a_halt(self):
        self.login(self.admin)
        response = self.client.post(
            self.edit_url, self._payload(arrival_offset=300, departure_offset=310)
        )
        self.assertEqual(response.status_code, 302)
        self.halt.refresh_from_db()
        self.assertEqual(self.halt.arrival_offset, 300)
        self.assertEqual(self.halt.halt_minutes, 10)

    def test_duplicate_sequence_redisplays_the_form_with_an_error(self):
        create_route_station(
            route=self.route, station=create_station(station_code="BPL"), sequence_number=7
        )
        self.login(self.station_manager)
        response = self.client.post(self.edit_url, self._payload(sequence_number=7))
        self.assertEqual(response.status_code, 200)
        self.assertIn("sequence_number", response.context["form"].errors)

    def test_add_form_prefills_the_route_and_next_stop_number(self):
        self.login(self.station_manager)
        response = self.client.get(self.add_url, {"route": self.route.pk})
        self.assertEqual(response.status_code, 200)
        initial = response.context["form"].initial
        self.assertEqual(initial["route"], self.route.pk)
        self.assertEqual(initial["sequence_number"], 3)

    def test_prefilled_stop_number_starts_at_one_on_an_empty_route(self):
        empty = create_route(route_name="Fresh Corridor")
        self.login(self.station_manager)
        response = self.client.get(self.add_url, {"route": empty.pk})
        self.assertEqual(response.context["form"].initial["sequence_number"], 1)

    def test_a_bogus_route_query_value_is_ignored(self):
        self.login(self.station_manager)
        response = self.client.get(self.add_url, {"route": "'; drop table"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("route", response.context["form"].initial)

    # -- delete --------------------------------------------------------
    def test_delete_shows_a_confirmation_before_acting(self):
        self.login(self.station_manager)
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(RouteStation.objects.filter(pk=self.halt.pk).exists())

    def test_post_deletes_the_halt_and_returns_to_the_route(self):
        self.login(self.admin)
        response = self.client.post(self.delete_url)
        self.assertRedirects(
            response, reverse("railway:route_detail", args=[self.route.pk])
        )
        self.assertFalse(RouteStation.objects.filter(pk=self.halt.pk).exists())

    def test_station_manager_deleting_a_halt_lands_on_the_halt_list(self):
        self.login(self.station_manager)
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, f"{self.list_url}?route={self.route.pk}")
        self.assertFalse(RouteStation.objects.filter(pk=self.halt.pk).exists())

    # -- list behaviour ------------------------------------------------
    def test_route_filter_narrows_the_list(self):
        other = create_route(route_name="Delhi - Bhopal")
        create_route_station(route=other, sequence_number=1)
        self.login(self.admin)
        response = self.client.get(self.list_url, {"route": self.route.pk})
        routes = {h.route_id for h in response.context["halts"]}
        self.assertEqual(routes, {self.route.pk})

    def test_station_filter_narrows_the_list(self):
        create_route_station(route=create_route(), sequence_number=1)
        self.login(self.admin)
        response = self.client.get(self.list_url, {"station": self.station.pk})
        stations = {h.station_id for h in response.context["halts"]}
        self.assertEqual(stations, {self.station.pk})

    def test_search_matches_the_station_code(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"q": "KOTA"})
        self.assertEqual(len(response.context["halts"]), 1)

    def test_unknown_sort_value_falls_back_to_the_default(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"sort": "route__secret"})
        self.assertEqual(response.status_code, 200)

    def test_empty_list_renders_an_empty_state(self):
        RouteStation.objects.all().delete()
        self.login(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No route halts yet")
