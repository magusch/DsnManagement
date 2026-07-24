from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Place, PlaceKeyword, TestEventPlace, PlaceSchedule,
    District, DistrictKeyword,
)

from datetime import timedelta


class PlaceScheduleInline(admin.TabularInline):
    model = PlaceSchedule
    extra = 0
    fields = ('schedule_type', 'weekday', 'date', 'open_time', 'close_time')
    ordering = ['weekday', 'date']
    verbose_name = "Schedule"
    verbose_name_plural = "Schedule"
    show_change_link = True

    def get_extra(self, request, obj=None, **kwargs):
        if obj and obj.schedules.exists():
            return 2
        return super().get_extra(request, obj, **kwargs)


class PlaceAdmin(admin.ModelAdmin):
    list_display = [str, 'place_name', 'main_place', 'district', 'category', 'place_url', 'url_to_address']
    list_editable = ['category']
    list_filter = ['place_city', 'district', 'main_place']
    search_fields = ["place_name", "place_address", "place_metro", "category", "district_raw"]
    autocomplete_fields = ['main_place', 'district']
    inlines = [PlaceScheduleInline]
    readonly_fields = ("get_schedule_str",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        PlaceKeyword.objects.create(place_id=obj.id, place_keyword=obj.place_name)

    def save_formset(self, request, form, formset, change):
        for form in formset.forms:
            if form.cleaned_data.get('DELETE', False):  # Проверяем, что объект помечен для удаления
                instance = form.instance
                instance.delete()

        instances = formset.save(commit=False)

        for instance in instances:
            if instance.weekday is not None or instance.date or instance.schedule_type == 'hol':
                instance.save()
            else:
                if instance.pk:
                    instance.delete()

        formset.deleted_objects = [
            obj for obj in instances if obj.weekday is None and not obj.date
        ]

        formset.save_m2m()


class PlaceScheduleAdmin(admin.ModelAdmin):
    list_display = [str, 'place', "open_time", "close_time", ]
    actions = ['duplicate_schedule']
    list_editable = ["open_time", "close_time", ]

    def duplicate_schedule(self, request, queryset):
        duplicates = []
        for schedule in queryset:
            if schedule.schedule_type == 'std' and schedule.weekday is not None:
                weekdays = range(0, 7)
                for day in weekdays:
                    if day != schedule.weekday:
                        if not PlaceSchedule.objects.filter(
                                place=schedule.place,
                                schedule_type='std',
                                weekday=day
                        ).exists():
                            duplicates.append(
                                PlaceSchedule(
                                    place=schedule.place,
                                    schedule_type=schedule.schedule_type,
                                    weekday=day,
                                    open_time=schedule.open_time,
                                    close_time=schedule.close_time,
                                )
                            )
            elif schedule.schedule_type in ('hol', 'spl') and schedule.date:
                new_date = schedule.date + timedelta(days=1)
                if not PlaceSchedule.objects.filter(
                        place=schedule.place,
                        schedule_type='hol',
                        date=new_date
                ).exists():
                    duplicates.append(
                        PlaceSchedule(
                            place=schedule.place,
                            schedule_type=schedule.schedule_type,
                            date=new_date,
                            open_time=schedule.open_time,
                            close_time=schedule.close_time,
                        )
                    )
        # Сохраняем все новые записи
        PlaceSchedule.objects.bulk_create(duplicates)
        self.message_user(
            request,
            f"Успешно продублировано {len(duplicates)} расписаний!"
        )


class PlaceKeywordAdmin(admin.ModelAdmin):
    readonly_fields = ('place_searching',)

    class Media:
        js = ('admin_place_searching.js',)

    def place_searching(self, obj):
        return format_html('<input type="text" class="place-autocomplete" /></input>'
                           '<div id="place-autocomplete-results" class="form-row"></div>')


class DistrictKeywordInline(admin.TabularInline):
    model = DistrictKeyword
    extra = 1
    fields = ('district_keyword',)


class DistrictAdmin(admin.ModelAdmin):
    list_display = ['name', 'place_city', 'parent']
    list_filter = ['place_city']
    search_fields = ['name', 'place_city', 'keywords__district_keyword']
    autocomplete_fields = ['parent']
    inlines = [DistrictKeywordInline]


class DistrictKeywordAdmin(admin.ModelAdmin):
    list_display = ['district_keyword', 'district']
    search_fields = ['district_keyword', 'district__name']
    autocomplete_fields = ['district']


admin.site.register(Place, PlaceAdmin)
admin.site.register(PlaceKeyword, PlaceKeywordAdmin)
admin.site.register(PlaceSchedule, PlaceScheduleAdmin)
admin.site.register(District, DistrictAdmin)
admin.site.register(DistrictKeyword, DistrictKeywordAdmin)
