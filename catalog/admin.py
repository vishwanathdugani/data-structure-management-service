"""
Django admin registration.

The admin is a convenience for inspecting the catalog locally, not a second write path:
model-level constraints still apply here, but the lifecycle and PII rules from
`catalog/services/rules.py` do not, because the admin talks to the ORM directly. That is a
deliberate trade-off for a support tool, and the reason `lifecycle_status` is shown but
audit fields are read-only.
"""

from django.contrib import admin

from catalog.models import DataElement, Dataset


class DataElementInline(admin.TabularInline):
    model = DataElement
    extra = 0
    fields = ("name", "data_type", "max_length", "is_nullable", "is_primary_key", "is_pii")
    show_change_link = True


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "lifecycle_status",
        "retention_period_days",
        "data_element_count",
        "created_at",
    )
    list_filter = ("lifecycle_status",)
    search_fields = ("name", "description", "owner")
    readonly_fields = ("uuid", "created_at", "updated_at")
    inlines = (DataElementInline,)

    def get_queryset(self, request):
        # Annotate once for the whole changelist instead of counting per row.
        return super().get_queryset(request).with_data_element_count()

    @admin.display(description="Data elements", ordering="data_element_count")
    def data_element_count(self, obj: Dataset) -> int:
        return obj.data_element_count


@admin.register(DataElement)
class DataElementAdmin(admin.ModelAdmin):
    list_display = ("name", "dataset", "data_type", "is_nullable", "is_primary_key", "is_pii")
    list_filter = ("data_type", "is_pii", "is_nullable", "is_primary_key")
    search_fields = ("name", "description", "dataset__name")
    list_select_related = ("dataset",)
    readonly_fields = ("uuid", "created_at", "updated_at")
    autocomplete_fields = ("dataset",)
