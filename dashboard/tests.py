"""Dashboard tests: every figure on the landing page comes from the database."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from accounts.factories import RailCoreTestCase
from activity_logs.models import ActivityLog
from notifications.models import Notification
from railway.factories import (
    create_platform,
    create_route,
    create_route_station,
    create_schedule,
    create_station,
    create_train,
)
from railway.models import Train


def _card(response, label):
    """The headline stat card carrying *label*."""
    for card in response.context["stat_cards"]:
        if card["label"] == label:
            return card
    raise AssertionError(f"No stat card labelled {label!r}")


def _status_row(response, label):
    for row in response.context["system_status"]:
        if row["label"] == label:
            return row
    raise AssertionError(f"No system status row labelled {label!r}")


def _today_at(hour, minute=0):
    """A timezone aware stamp at *hour* today, in the server's local time."""
    return timezone.localtime(timezone.now()).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


class DashboardBase(RailCoreTestCase):
    def setUp(self):
        self.url = reverse("dashboard:home")

    def open_as(self, user):
        self.login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response


class DashboardAccessTests(DashboardBase):
    def test_anonymous_visitors_are_sent_to_sign_in(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])
        self.assertIn(self.url, response["Location"])

    def test_every_role_can_open_the_dashboard(self):
        for user in (
            self.admin,
            self.railway_manager,
            self.station_manager,
            self.operations_staff,
        ):
            with self.subTest(role=user.role_name):
                self.assertAllowed(self.url, user)

    def test_an_account_without_a_role_still_lands_somewhere_useful(self):
        from accounts.factories import create_user

        orphan = create_user("no_role_yet")
        response = self.open_as(orphan)
        self.assertEqual(response.context["quick_actions"], [])

    def test_the_page_is_titled_and_dated(self):
        response = self.open_as(self.admin)
        self.assertEqual(response.context["page_title"], "Dashboard")
        self.assertEqual(response.context["active_nav"], "dashboard")
        self.assertIn(
            f"{timezone.localtime(timezone.now()):%Y}", response.context["page_subtitle"]
        )


class StatCardTests(DashboardBase):
    def test_all_six_cards_are_present_in_order(self):
        response = self.open_as(self.admin)
        labels = [card["label"] for card in response.context["stat_cards"]]
        self.assertEqual(
            labels,
            [
                "Active Stations",
                "Total Trains",
                "Active Trains",
                "Active Routes",
                "Today's Schedules",
                "Cancelled Schedules",
            ],
        )

    def test_an_empty_database_shows_zeroes_not_placeholders(self):
        response = self.open_as(self.admin)
        for card in response.context["stat_cards"]:
            with self.subTest(card=card["label"]):
                self.assertEqual(card["value"], 0)

    def test_active_stations_counts_only_the_open_ones(self):
        create_station()
        create_station()
        create_station(is_active=False)

        card = _card(self.open_as(self.admin), "Active Stations")
        self.assertEqual(card["value"], 2)
        self.assertIn("3 recorded in total", card["meta"])

    def test_total_trains_excludes_the_archive(self):
        create_train()
        create_train()
        create_train().soft_delete()

        card = _card(self.open_as(self.admin), "Total Trains")
        self.assertEqual(card["value"], 2)
        self.assertIn("1 archived", card["meta"])

    def test_active_trains_counts_only_running_rakes(self):
        create_train(status=Train.ACTIVE)
        create_train(status=Train.MAINTENANCE)
        create_train(status=Train.INACTIVE)

        card = _card(self.open_as(self.admin), "Active Trains")
        self.assertEqual(card["value"], 1)
        self.assertIn("33.3%", card["meta"])

    def test_active_routes_counts_only_live_corridors(self):
        create_route()
        create_route(is_active=False)

        card = _card(self.open_as(self.admin), "Active Routes")
        self.assertEqual(card["value"], 1)
        self.assertIn("2 defined in total", card["meta"])

    def test_todays_schedules_counts_departures_dated_today(self):
        create_schedule(departure=_today_at(6), arrival=_today_at(11))
        create_schedule(
            platform=create_platform(),
            departure=_today_at(20),
            arrival=_today_at(23),
        )
        create_schedule(
            platform=create_platform(),
            departure=_today_at(9) + timedelta(days=1),
            arrival=_today_at(14) + timedelta(days=1),
        )
        create_schedule(
            platform=create_platform(),
            departure=_today_at(9) - timedelta(days=1),
            arrival=_today_at(14) - timedelta(days=1),
        )

        card = _card(self.open_as(self.admin), "Today's Schedules")
        self.assertEqual(card["value"], 2)

    def test_cancelled_schedules_counts_only_todays_cancellations(self):
        create_schedule(departure=_today_at(6), arrival=_today_at(11))
        create_schedule(
            platform=create_platform(),
            departure=_today_at(8),
            arrival=_today_at(12),
            is_cancelled=True,
        )
        create_schedule(
            platform=create_platform(),
            departure=_today_at(8) + timedelta(days=1),
            arrival=_today_at(12) + timedelta(days=1),
            is_cancelled=True,
        )

        response = self.open_as(self.admin)
        card = _card(response, "Cancelled Schedules")
        self.assertEqual(card["value"], 1)
        self.assertEqual(card["tone"], "danger")
        self.assertIn("50.0%", card["meta"])

    def test_the_cancellation_card_stays_calm_when_nothing_is_cancelled(self):
        create_schedule(departure=_today_at(6), arrival=_today_at(11))
        card = _card(self.open_as(self.admin), "Cancelled Schedules")
        self.assertEqual(card["value"], 0)
        self.assertEqual(card["tone"], "neutral")

    def test_a_card_the_role_cannot_open_is_not_a_link(self):
        response = self.open_as(self.station_manager)
        self.assertEqual(_card(response, "Total Trains")["url"], "")
        self.assertEqual(_card(response, "Active Routes")["url"], "")
        self.assertEqual(
            _card(response, "Active Stations")["url"], reverse("railway:station_list")
        )

    def test_the_administrator_gets_every_card_as_a_link(self):
        response = self.open_as(self.admin)
        for card in response.context["stat_cards"]:
            with self.subTest(card=card["label"]):
                self.assertTrue(card["url"])


class ChartTests(DashboardBase):
    def test_the_week_chart_covers_the_next_seven_days(self):
        response = self.open_as(self.admin)
        rows = response.context["week_rows"]
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["label"], "Today")
        self.assertEqual(rows[1]["label"], "Tomorrow")

    def test_the_week_chart_counts_real_departures(self):
        create_schedule(departure=_today_at(6), arrival=_today_at(11))
        create_schedule(
            platform=create_platform(),
            departure=_today_at(9) + timedelta(days=2),
            arrival=_today_at(14) + timedelta(days=2),
        )

        response = self.open_as(self.admin)
        rows = response.context["week_rows"]
        self.assertEqual(rows[0]["total"], 1)
        self.assertEqual(rows[2]["total"], 1)
        self.assertEqual(response.context["week_total"], 2)
        self.assertEqual(response.context["week_peak"], 1)

    def test_a_fully_cancelled_day_is_flagged(self):
        create_schedule(
            departure=_today_at(6), arrival=_today_at(11), is_cancelled=True
        )
        rows = self.open_as(self.admin).context["week_rows"]
        self.assertEqual(rows[0]["cancelled"], 1)
        self.assertEqual(rows[0]["tone"], "danger")

    def test_bar_percentages_are_relative_to_the_busiest_day(self):
        create_schedule(departure=_today_at(6), arrival=_today_at(11))
        create_schedule(
            platform=create_platform(), departure=_today_at(9), arrival=_today_at(12)
        )
        create_schedule(
            platform=create_platform(),
            departure=_today_at(9) + timedelta(days=1),
            arrival=_today_at(12) + timedelta(days=1),
        )

        rows = self.open_as(self.admin).context["week_rows"]
        self.assertEqual(rows[0]["percent"], 100)
        self.assertEqual(rows[1]["percent"], 50.0)

    def test_an_empty_week_draws_no_bars(self):
        rows = self.open_as(self.admin).context["week_rows"]
        self.assertEqual([row["percent"] for row in rows], [0] * 7)

    def test_the_fleet_donut_counts_each_status(self):
        create_train(status=Train.ACTIVE)
        create_train(status=Train.ACTIVE)
        create_train(status=Train.MAINTENANCE)
        create_train(status=Train.INACTIVE).soft_delete()

        fleet = self.open_as(self.admin).context["fleet"]
        values = {segment["status"]: segment["value"] for segment in fleet["segments"]}
        self.assertEqual(values[Train.ACTIVE], 2)
        self.assertEqual(values[Train.MAINTENANCE], 1)
        self.assertEqual(values[Train.INACTIVE], 0)
        self.assertEqual(fleet["total"], 3)
        self.assertEqual(fleet["active_percent"], 66.7)

    def test_the_fleet_donut_survives_an_empty_fleet(self):
        fleet = self.open_as(self.admin).context["fleet"]
        self.assertEqual(fleet["total"], 0)
        self.assertEqual(fleet["active_percent"], 0)
        self.assertTrue(all(segment["percent"] == 0 for segment in fleet["segments"]))

    def test_busiest_routes_are_ranked_by_the_trains_working_them(self):
        busy = create_route(route_name="Delhi - Mumbai Central")
        quiet = create_route(route_name="Delhi - Bhopal")
        create_train(route=busy)
        create_train(route=busy)
        create_train(route=quiet)

        rows = self.open_as(self.admin).context["busiest_routes"]
        self.assertEqual([row["route"] for row in rows], [busy, quiet])
        self.assertEqual([row["count"] for row in rows], [2, 1])
        self.assertEqual([row["percent"] for row in rows], [100, 50.0])

    def test_routes_without_trains_are_left_out(self):
        create_route(route_name="Unused Corridor")
        self.assertEqual(self.open_as(self.admin).context["busiest_routes"], [])

    def test_punctuality_splits_recent_runs_three_ways(self):
        yesterday = timezone.now() - timedelta(days=1)
        create_schedule(departure=yesterday, arrival=yesterday + timedelta(hours=2))
        create_schedule(
            platform=create_platform(),
            departure=yesterday,
            arrival=yesterday + timedelta(hours=2),
            delay_minutes=30,
        )
        create_schedule(
            platform=create_platform(),
            departure=yesterday,
            arrival=yesterday + timedelta(hours=2),
            is_cancelled=True,
        )

        punctuality = self.open_as(self.admin).context["punctuality"]
        self.assertEqual(punctuality["total"], 3)
        self.assertEqual(punctuality["on_time"], 1)
        self.assertEqual(punctuality["delayed"], 1)
        self.assertEqual(punctuality["cancelled"], 1)
        self.assertEqual(punctuality["on_time_percent"], 33.3)
        self.assertEqual(punctuality["average_delay"], 30.0)
        self.assertEqual(punctuality["tone"], "danger")

    def test_punctuality_ignores_runs_older_than_the_window(self):
        old = timezone.now() - timedelta(days=30)
        create_schedule(departure=old, arrival=old + timedelta(hours=2))
        punctuality = self.open_as(self.admin).context["punctuality"]
        self.assertEqual(punctuality["total"], 0)
        self.assertEqual(punctuality["window_days"], 7)

    def test_a_clean_week_reads_as_healthy(self):
        create_schedule(departure=_today_at(6), arrival=_today_at(11))
        punctuality = self.open_as(self.admin).context["punctuality"]
        self.assertEqual(punctuality["on_time_percent"], 100)
        self.assertEqual(punctuality["tone"], "success")
        self.assertEqual(punctuality["average_delay"], 0)


class ActivityFeedTests(DashboardBase):
    def test_the_feed_shows_the_newest_entries_first(self):
        self.login(self.admin)
        ActivityLog.objects.create(
            user=self.admin, action=ActivityLog.CREATE, description="Older entry"
        )
        newest = ActivityLog.objects.create(
            user=self.admin, action=ActivityLog.DELETE, description="Newest entry"
        )

        feed = self.client.get(self.url).context["activity_feed"]
        self.assertEqual(feed[0]["log"], newest)

    def test_signing_in_appears_in_the_feed(self):
        response = self.open_as(self.railway_manager)
        descriptions = [row["log"].description for row in response.context["activity_feed"]]
        self.assertTrue(any("signed in" in text for text in descriptions))

    def test_each_entry_carries_its_icon_and_tone(self):
        self.login(self.admin)
        ActivityLog.objects.create(
            user=self.admin, action=ActivityLog.DELETE, description="Removed something"
        )
        row = self.client.get(self.url).context["activity_feed"][0]
        self.assertEqual(row["icon"], "trash")
        self.assertEqual(row["tone"], "danger")

    def test_an_entry_without_an_actor_reads_as_system(self):
        self.login(self.admin)
        ActivityLog.objects.create(
            user=None, action=ActivityLog.UPDATE, description="Automated cleanup"
        )
        row = self.client.get(self.url).context["activity_feed"][0]
        self.assertEqual(row["actor"], "System")

    def test_the_feed_is_capped(self):
        self.login(self.admin)
        for index in range(12):
            ActivityLog.objects.create(
                user=self.admin, action=ActivityLog.CREATE, description=f"Entry {index}"
            )
        self.assertEqual(len(self.client.get(self.url).context["activity_feed"]), 8)


class SystemStatusTests(DashboardBase):
    def test_the_database_row_is_always_healthy(self):
        row = _status_row(self.open_as(self.admin), "Database")
        self.assertEqual(row["value"], "Connected")
        self.assertEqual(row["state"], "ok")

    def test_rakes_in_maintenance_are_reported(self):
        create_train(status=Train.MAINTENANCE)
        row = _status_row(self.open_as(self.admin), "Rakes in maintenance")
        self.assertEqual(row["value"], "1 train")
        self.assertEqual(row["state"], "warn")

    def test_closed_platforms_are_reported(self):
        station = create_station()
        create_platform(station=station, platform_number=1)
        create_platform(station=station, platform_number=2, is_active=False)

        row = _status_row(self.open_as(self.admin), "Platforms closed")
        self.assertEqual(row["value"], "1 platform")
        self.assertEqual(row["state"], "warn")

    def test_runs_delayed_right_now_are_reported(self):
        create_schedule(
            departure=timezone.now() + timedelta(hours=1),
            arrival=timezone.now() + timedelta(hours=4),
            delay_minutes=20,
        )
        row = _status_row(self.open_as(self.admin), "Runs delayed now")
        self.assertEqual(row["value"], "1 run")
        self.assertEqual(row["state"], "warn")

    def test_a_delay_that_has_already_arrived_is_no_longer_live(self):
        past = timezone.now() - timedelta(hours=6)
        create_schedule(
            departure=past, arrival=past + timedelta(hours=2), delay_minutes=20
        )
        row = _status_row(self.open_as(self.admin), "Runs delayed now")
        self.assertEqual(row["value"], "0 runs")
        self.assertEqual(row["state"], "ok")

    def test_todays_cancellations_take_the_service_down(self):
        create_schedule(
            departure=_today_at(7), arrival=_today_at(10), is_cancelled=True
        )
        row = _status_row(self.open_as(self.admin), "Cancellations today")
        self.assertEqual(row["value"], "1 run")
        self.assertEqual(row["state"], "down")

    def test_routes_without_halts_are_flagged(self):
        bare = create_route(route_name="Bare Corridor")
        stopped = create_route(route_name="Stopping Corridor")
        create_route_station(route=stopped, sequence_number=1)

        row = _status_row(self.open_as(self.admin), "Routes without halts")
        self.assertEqual(row["value"], "1 route")
        self.assertEqual(row["state"], "warn")
        self.assertTrue(bare.pk and stopped.pk)

    def test_a_quiet_network_reports_no_warnings(self):
        rows = self.open_as(self.admin).context["system_status"]
        self.assertEqual({row["state"] for row in rows}, {"ok"})


class QuickActionTests(DashboardBase):
    def _labels(self, user):
        return [action["label"] for action in self.open_as(user).context["quick_actions"]]

    def test_the_administrator_sees_every_shortcut(self):
        self.assertEqual(
            self._labels(self.admin),
            [
                "Add Train",
                "Add Schedule",
                "Add Route",
                "Add Station",
                "Add Platform",
                "Add Route Halt",
                "Add Employee",
                "Activity Log",
            ],
        )

    def test_the_railway_manager_owns_rolling_stock_and_the_plan(self):
        self.assertEqual(
            self._labels(self.railway_manager),
            ["Add Train", "Add Schedule", "Add Route", "Activity Log"],
        )

    def test_the_station_manager_owns_infrastructure(self):
        self.assertEqual(
            self._labels(self.station_manager),
            ["Add Station", "Add Platform", "Add Route Halt"],
        )

    def test_operations_staff_only_book_runs(self):
        self.assertEqual(self._labels(self.operations_staff), ["Add Schedule"])

    def test_every_shortcut_points_at_a_real_url(self):
        for action in self.open_as(self.admin).context["quick_actions"]:
            with self.subTest(action=action["label"]):
                self.assertTrue(action["url"].startswith("/"))


class NextDeparturesTests(DashboardBase):
    def test_only_upcoming_runs_are_listed_soonest_first(self):
        now = timezone.now()
        later = create_schedule(
            departure=now + timedelta(hours=5), arrival=now + timedelta(hours=9)
        )
        sooner = create_schedule(
            platform=create_platform(),
            departure=now + timedelta(hours=1),
            arrival=now + timedelta(hours=4),
        )
        create_schedule(
            platform=create_platform(),
            departure=now - timedelta(hours=3),
            arrival=now - timedelta(hours=1),
        )

        departures = list(self.open_as(self.admin).context["next_departures"])
        self.assertEqual(departures, [sooner, later])

    def test_cancelled_runs_are_left_out(self):
        now = timezone.now()
        create_schedule(
            departure=now + timedelta(hours=1),
            arrival=now + timedelta(hours=4),
            is_cancelled=True,
        )
        self.assertEqual(list(self.open_as(self.admin).context["next_departures"]), [])

    def test_the_board_is_capped_at_six(self):
        now = timezone.now()
        for index in range(8):
            create_schedule(
                platform=create_platform(),
                departure=now + timedelta(hours=index + 1),
                arrival=now + timedelta(hours=index + 3),
            )
        self.assertEqual(len(self.open_as(self.admin).context["next_departures"]), 6)


class NetworkSummaryTests(DashboardBase):
    def test_every_figure_is_counted_from_the_database(self):
        station = create_station()
        platform = create_platform(station=station, platform_number=1)
        create_platform(station=station, platform_number=2)
        route = create_route(
            route_name="Delhi - Bhopal",
            source_station=station,
            destination_station=create_station(),
        )
        create_route_station(route=route, station=station, sequence_number=1)
        create_train(route=route, total_coaches=14)
        create_schedule(
            train=create_train(total_coaches=6, route=route), platform=platform
        )

        network = self.open_as(self.admin).context["network"]
        self.assertEqual(network["stations"], 2)
        self.assertEqual(network["platforms"], 2)
        self.assertEqual(network["routes"], 1)
        self.assertEqual(network["halts"], 1)
        self.assertEqual(network["trains"], 2)
        self.assertEqual(network["schedules"], 1)
        self.assertEqual(network["coaches"], 20)
        self.assertEqual(float(network["distance"]), 450.50)

    def test_archived_trains_are_left_out_of_the_summary(self):
        create_train(total_coaches=10)
        create_train(total_coaches=10).soft_delete()

        network = self.open_as(self.admin).context["network"]
        self.assertEqual(network["trains"], 1)
        self.assertEqual(network["coaches"], 10)

    def test_the_employee_count_ignores_deleted_accounts(self):
        self.assertEqual(self.open_as(self.admin).context["network"]["employees"], 4)

        self.operations_staff.soft_delete()
        self.assertEqual(self.open_as(self.admin).context["network"]["employees"], 3)

    def test_an_empty_network_reports_zero_distance_and_coaches(self):
        network = self.open_as(self.admin).context["network"]
        self.assertEqual(network["distance"], 0)
        self.assertEqual(network["coaches"], 0)


class UnreadBadgeTests(DashboardBase):
    def test_the_badge_counts_only_this_employees_unread_notifications(self):
        Notification.objects.create(user=self.admin, title="For me", message="Body")
        Notification.objects.create(
            user=self.admin, title="Already seen", message="Body", is_read=True
        )
        Notification.objects.create(
            user=self.operations_staff, title="Not mine", message="Body"
        )

        self.assertEqual(self.open_as(self.admin).context["unread_notifications"], 1)

    def test_the_badge_is_zero_for_a_clean_inbox(self):
        self.assertEqual(self.open_as(self.admin).context["unread_notifications"], 0)
