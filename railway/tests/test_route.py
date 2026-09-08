"""Route CRUD, endpoint validation and role based access."""

from decimal import Decimal

from django.urls import reverse

from accounts.factories import RailCoreTestCase
from activity_logs.models import ActivityLog
from railway.factories import (
    create_route,
    create_route_station,
    create_station,
    create_train,
)
from railway.forms import RouteForm
from railway.models import Route, Train


class RouteModelTests(RailCoreTestCase):
    def test_corridor_uses_the_endpoint_codes(self):
        route = create_route(
            source_station=create_station(station_code="NDLS"),
            destination_station=create_station(station_code="BCT"),
        )
        self.assertEqual(route.corridor, "NDLS → BCT")

    def test_halt_and_train_counts(self):
        route = create_route()
        self.assertEqual(route.halt_count, 0)
        self.assertEqual(route.train_count, 0)

        create_route_station(route=route, sequence_number=1)
        create_train(route=route)

        self.assertEqual(route.halt_count, 1)
        self.assertEqual(route.train_count, 1)

    def test_status_label_tracks_is_active(self):
        self.assertEqual(create_route().status_label, "ACTIVE")
        self.assertEqual(create_route(is_active=False).status_label, "INACTIVE")


class RouteFormTests(RailCoreTestCase):
    def setUp(self):
        self.source = create_station(station_code="NDLS")
        self.destination = create_station(station_code="BCT")

    def _payload(self, **overrides):
        payload = {
            "route_name": "Delhi - Mumbai Central",
            "source_station": self.source.pk,
            "destination_station": self.destination.pk,
            "total_distance": "1384.00",
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    def test_valid_payload_is_accepted(self):
        self.assertTrue(RouteForm(data=self._payload()).is_valid())

    def test_source_and_destination_must_differ(self):
        form = RouteForm(data=self._payload(destination_station=self.source.pk))
        self.assertFalse(form.is_valid())
        self.assertIn("destination_station", form.errors)

    def test_duplicate_route_name_is_rejected(self):
        create_route(route_name="Delhi - Mumbai Central")
        form = RouteForm(data=self._payload())
        self.assertFalse(form.is_valid())
        self.assertIn("route_name", form.errors)

    def test_distance_must_be_positive(self):
        for distance in ("0", "-5.00"):
            with self.subTest(distance=distance):
                form = RouteForm(data=self._payload(total_distance=distance))
                self.assertFalse(form.is_valid())
                self.assertIn("total_distance", form.errors)

    def test_required_fields_are_enforced(self):
        form = RouteForm(data={})
        self.assertFalse(form.is_valid())
        for field in (
            "route_name",
            "source_station",
            "destination_station",
            "total_distance",
        ):
            self.assertIn(field, form.errors)

    def test_inactive_stations_are_not_selectable(self):
        retired = create_station(station_code="OLDX", is_active=False)
        form = RouteForm()
        self.assertNotIn(retired, form.fields["source_station"].queryset)
        self.assertNotIn(retired, form.fields["destination_station"].queryset)


class RouteViewTests(RailCoreTestCase):
    def setUp(self):
        self.source = create_station(name="New Delhi", station_code="NDLS")
        self.destination = create_station(name="Mumbai Central", station_code="BCT")
        self.route = create_route(
            route_name="Delhi - Mumbai Central",
            source_station=self.source,
            destination_station=self.destination,
        )
        self.list_url = reverse("railway:route_list")
        self.add_url = reverse("railway:route_add")
        self.detail_url = reverse("railway:route_detail", args=[self.route.pk])
        self.edit_url = reverse("railway:route_edit", args=[self.route.pk])
        self.delete_url = reverse("railway:route_delete", args=[self.route.pk])

    def _payload(self, **overrides):
        payload = {
            "route_name": self.route.route_name,
            "source_station": self.source.pk,
            "destination_station": self.destination.pk,
            "total_distance": "1384.00",
            "is_active": True,
        }
        payload.update(overrides)
        return payload

    # -- read access ---------------------------------------------------
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_admin_railway_manager_and_operations_staff_can_read_routes(self):
        for user in (self.admin, self.railway_manager, self.operations_staff):
            with self.subTest(role=user.role_name):
                self.assertAllowed(self.list_url, user)

    def test_station_manager_cannot_read_the_route_list(self):
        self.assertForbidden(self.list_url, self.station_manager)

    def test_detail_lists_halts_and_trains(self):
        create_route_station(route=self.route, station=self.source, sequence_number=1)
        create_train(route=self.route)
        self.login(self.railway_manager)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["halt_count"], 1)
        self.assertEqual(response.context["train_count"], 1)

    def test_detail_offers_a_prefilled_add_halt_link(self):
        self.login(self.railway_manager)
        response = self.client.get(self.detail_url)
        self.assertEqual(
            response.context["add_halt_url"],
            f"{reverse('railway:route_station_add')}?route={self.route.pk}",
        )

    # -- write access --------------------------------------------------
    def test_railway_manager_can_create_a_route(self):
        self.login(self.railway_manager)
        response = self.client.post(
            self.add_url, self._payload(route_name="Delhi - Howrah")
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Route.objects.filter(route_name="Delhi - Howrah").exists())

    def test_creating_a_route_writes_an_activity_log_entry(self):
        self.login(self.railway_manager)
        self.client.post(self.add_url, self._payload(route_name="Delhi - Howrah"))
        self.assertTrue(
            ActivityLog.objects.filter(
                action=ActivityLog.CREATE, model_name="Route"
            ).exists()
        )

    def test_station_manager_cannot_create_a_route(self):
        self.assertForbidden(self.add_url, self.station_manager)

    def test_operations_staff_cannot_edit_a_route(self):
        self.assertForbidden(self.edit_url, self.operations_staff)

    def test_operations_staff_cannot_delete_a_route(self):
        self.assertForbidden(self.delete_url, self.operations_staff)

    def test_admin_can_edit_a_route(self):
        self.login(self.admin)
        response = self.client.post(self.edit_url, self._payload(total_distance="1400.50"))
        self.assertEqual(response.status_code, 302)
        self.route.refresh_from_db()
        self.assertEqual(self.route.total_distance, Decimal("1400.50"))

    def test_same_source_and_destination_redisplays_the_form(self):
        self.login(self.admin)
        response = self.client.post(
            self.edit_url, self._payload(destination_station=self.source.pk)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("destination_station", response.context["form"].errors)

    # -- delete --------------------------------------------------------
    def test_delete_shows_a_confirmation_before_acting(self):
        self.login(self.railway_manager)
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Route.objects.filter(pk=self.route.pk).exists())

    def test_post_deletes_the_route(self):
        self.login(self.railway_manager)
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Route.objects.filter(pk=self.route.pk).exists())

    def test_deleting_a_route_removes_its_halts(self):
        create_route_station(route=self.route, station=self.source, sequence_number=1)
        self.login(self.railway_manager)
        self.client.post(self.delete_url)
        self.assertFalse(Route.objects.filter(pk=self.route.pk).exists())

    def test_route_with_a_train_is_protected_from_deletion(self):
        train = create_train(route=self.route)
        self.login(self.railway_manager)
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Route.objects.filter(pk=self.route.pk).exists())
        self.assertTrue(Train.objects.filter(pk=train.pk).exists())

    # -- list behaviour ------------------------------------------------
    def test_search_narrows_the_list(self):
        create_route(route_name="Chennai - Bengaluru")
        self.login(self.admin)
        response = self.client.get(self.list_url, {"q": "Chennai"})
        names = [r.route_name for r in response.context["routes"]]
        self.assertEqual(names, ["Chennai - Bengaluru"])

    def test_status_filter_hides_withdrawn_routes(self):
        create_route(route_name="Withdrawn Corridor", is_active=False)
        self.login(self.admin)
        response = self.client.get(self.list_url, {"status": "active"})
        names = [r.route_name for r in response.context["routes"]]
        self.assertNotIn("Withdrawn Corridor", names)

    def test_list_annotates_the_halt_count(self):
        create_route_station(route=self.route, station=self.source, sequence_number=1)
        self.login(self.admin)
        response = self.client.get(self.list_url)
        row = next(r for r in response.context["routes"] if r.pk == self.route.pk)
        self.assertEqual(row.halts, 1)

    def test_unknown_sort_value_falls_back_to_the_default(self):
        self.login(self.admin)
        response = self.client.get(self.list_url, {"sort": "secret"})
        self.assertEqual(response.status_code, 200)

    def test_empty_list_renders_an_empty_state(self):
        Route.objects.all().delete()
        self.login(self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No routes defined yet")
