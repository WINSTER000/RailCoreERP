from django.contrib import admin

from .models import Platform, Route, RouteStation, Schedule, Station, Train


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("station_code", "name", "city", "state", "platform_count", "is_active")
    list_filter = ("is_active", "state")
    search_fields = ("name", "station_code", "city", "state")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Platforms")
    def platform_count(self, obj):
        return obj.platform_count


@admin.register(Platform)
class PlatformAdmin(admin.ModelAdmin):
    list_display = ("station", "platform_number", "is_active", "created_at")
    list_filter = ("is_active", "station")
    search_fields = ("station__name", "station__station_code", "platform_number")
    ordering = ("station__name", "platform_number")
    autocomplete_fields = ("station",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "route_name",
        "source_station",
        "destination_station",
        "total_distance",
        "halt_count",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = (
        "route_name",
        "source_station__name",
        "source_station__station_code",
        "destination_station__name",
        "destination_station__station_code",
    )
    ordering = ("route_name",)
    autocomplete_fields = ("source_station", "destination_station")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Halts")
    def halt_count(self, obj):
        return obj.halt_count


@admin.register(RouteStation)
class RouteStationAdmin(admin.ModelAdmin):
    list_display = (
        "route",
        "sequence_number",
        "station",
        "arrival_offset",
        "departure_offset",
        "halt_minutes",
    )
    list_filter = ("route",)
    search_fields = ("route__route_name", "station__name", "station__station_code")
    ordering = ("route__route_name", "sequence_number")
    autocomplete_fields = ("route", "station")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Halt (min)")
    def halt_minutes(self, obj):
        return obj.halt_minutes


@admin.register(Train)
class TrainAdmin(admin.ModelAdmin):
    list_display = (
        "train_number",
        "train_name",
        "route",
        "total_coaches",
        "status",
        "is_deleted",
        "created_at",
    )
    list_filter = ("status", "is_deleted", "route")
    search_fields = ("train_number", "train_name", "route__route_name")
    ordering = ("train_number",)
    autocomplete_fields = ("route",)
    readonly_fields = ("created_at", "updated_at")
    actions = ("restore_selected",)

    def get_queryset(self, request):
        # Soft deleted trains stay visible (and restorable) inside the admin.
        return Train.all_objects.get_queryset().select_related("route")

    @admin.action(description="Restore selected trains")
    def restore_selected(self, request, queryset):
        updated = queryset.update(is_deleted=False)
        self.message_user(request, f"{updated} train(s) restored.")


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "train",
        "platform",
        "departure_datetime",
        "arrival_datetime",
        "delay_minutes",
        "is_cancelled",
    )
    list_filter = ("is_cancelled", "platform__station", "train__status")
    search_fields = (
        "train__train_number",
        "train__train_name",
        "platform__station__name",
        "platform__station__station_code",
    )
    ordering = ("-departure_datetime",)
    date_hierarchy = "departure_datetime"
    autocomplete_fields = ("train", "platform")
    readonly_fields = ("created_at", "updated_at")
