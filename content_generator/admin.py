from django.contrib import admin, messages
from .models import FilterSet, EventSelection, PostTemplate, GeneratedPost, PostingSchedule
from .services import FilterService
from django.utils.translation import ngettext

from . import utils


@admin.register(FilterSet)
class FilterSetAdmin(admin.ModelAdmin):
    list_display = ['name', 'filter_type', 'created_by', 'is_active', 'created_at']
    list_filter = ['filter_type', 'is_active', 'created_at']
    exclude = ['created_at']
    search_fields = ['name', 'description']
    #readonly_fields = ['created_at']
    actions = ['apply_filter']

    def save_model(self, request, obj, form, change):
        if not change:  # Только при создании новой записи
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def apply_filter(self, request, queryset):
        ids = list(queryset.values_list('id', flat=True))
        answer = utils.event_selection_by_filter_id(ids)
        if answer:
            self.message_user(
                request,
                ngettext(
                    "%d event was successfully added for preparing to post.",
                    "%d events were successfully added for preparing to post.",
                    len(ids),
                )
                % len(ids),
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                ngettext(
                    "%d event wasn't added for preparing to post.",
                    "%d events weren't added for preparing to post.",
                    len(ids),
                )
                % len(ids),
                messages.ERROR,
            )


@admin.register(PostTemplate)
class PostTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']


@admin.register(GeneratedPost)
class GeneratedPostAdmin(admin.ModelAdmin):
    list_display = ['title', 'status', 'generated_by', 'created_at']
    list_filter = ['status', 'created_at']
    exclude = ['created_at', 'updated_at']
    search_fields = ['title', 'content']


@admin.register(PostingSchedule)
class PostingScheduleAdmin(admin.ModelAdmin):
    list_display = ['generated_post', 'status', 'scheduled_time', 'is_posted', 'retry_count']
    list_filter = ['platform', 'is_posted', 'scheduled_time']
    list_editable = ["scheduled_time", "status"]
    readonly_fields = ['posted_at']
    exclude = ['created_at', 'updated_at']


@admin.action(description="Сгенерировать пост по шаблону")
def generate_post_action(modeladmin, request, queryset):
    template = PostTemplate.objects.filter(is_active=True).first()  # или выбрать через форму
    if not template:
        messages.error(request, "Нет активного шаблона!")
        return

    for selection in queryset:
        events = selection.selected_events.all() # .filter(is_ready=True)
        content = utils.generate_post(events, template.template_text)
        GeneratedPost.objects.create(
            event_selection=selection,
            post_template=template,
            title=f"Подборка: {selection.name}",
            content=content,
            status='draft',
            generated_by=request.user
        )
    messages.success(request, "Посты успешно сгенерированы!")


@admin.register(EventSelection)
class EventSelectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'filter_set', 'status', 'created_by', 'created_at']
    list_filter = ['status', 'created_at']
    exclude = ['created_at']
    search_fields = ['name']
    filter_horizontal = ['selected_events']
    actions = [generate_post_action, 'generate_post_api']

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user

        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        obj = form.instance
        if obj.filter_set:
            existing_events = set(obj.selected_events.all())
            filtered_events = FilterService.apply_filters(obj.filter_set)
            all_events = existing_events.union(filtered_events)
            obj.selected_events.set(all_events)

    def generate_post_api(self, request, queryset):
        ids = list(queryset.values_list('id', flat=True))
        answer = utils.generate_post_api(ids[0], 1)
        if answer:
            self.message_user(
                request,
                ngettext(
                    "%d event was successfully added for generating post.",
                    "%d events were successfully added for generating post.",
                    len(ids),
                )
                % len(ids),
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                ngettext(
                    "%d event wasn't added for generating post.",
                    "%d events weren't added for generating post.",
                    len(ids),
                )
                % len(ids),
                messages.ERROR,
            )