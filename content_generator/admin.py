from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from city.admin_mixins import CityScopedAdmin
from events.helper.colors import css_color
from .models import FilterSet, EventSelection, PostTemplate, GeneratedPost, PostingSchedule
from .services import FilterService
from django.utils.translation import ngettext

from . import utils


@admin.register(FilterSet)
class FilterSetAdmin(CityScopedAdmin, admin.ModelAdmin):
    city_shared = True
    list_display = ['name', 'filter_type', 'created_by', 'is_active', 'created_at']
    list_filter = ['filter_type', 'is_active', 'created_at']
    exclude = ['created_at']
    search_fields = ['name', 'description']
    list_editable = ['is_active']
    #readonly_fields = ['created_at']
    actions = ['apply_filter']

    def save_model(self, request, obj, form, change):
        if not change:  # Только при создании новой записи
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def apply_filter(self, request, queryset):
        city = self.collection_city(request)
        if city is None:
            return
        ids = list(queryset.values_list('id', flat=True))
        answer = utils.event_selection_by_filter_id(ids, city)
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
class GeneratedPostAdmin(CityScopedAdmin, admin.ModelAdmin):
    list_display = ['title', 'status', 'generated_by', 'created_at']
    list_filter = ['status', 'created_at']
    exclude = ['created_at', 'updated_at']
    search_fields = ['title', 'content']
    readonly_fields = ['post_preview']

    change_list_template = "content_generator/generatedpost_change_list.html"
    change_form_template = "content_generator/change_form_with_preview.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        themes = self.admin_site.get_model_admin(FilterSet).scope_by_city(
            request, FilterSet.objects.filter(is_active=True))
        extra_context['theme_filter_sets'] = themes.order_by('name')
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description='Как будет выглядеть в канале')
    def post_preview(self, obj):
        if obj is None or not obj.pk:
            return '—'
        return obj.markdown_post_view_model()


PUBLISH_GRACE = timedelta(minutes=10)


def _human_delta(delta):
    minutes = round(abs(delta).total_seconds() / 60)
    days, minutes = divmod(minutes, 60 * 24)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if days:
        parts.append(f'{days} д')
    if hours:
        parts.append(f'{hours} ч')
    if minutes or not parts:
        parts.append(f'{minutes} мин')
    return ' '.join(parts)


class SlotFilter(admin.SimpleListFilter):
    """Slice the schedule the way it is actually read: what's next, what broke."""
    title = 'Слот'
    parameter_name = 'slot'

    def lookups(self, request, model_admin):
        return [
            ('upcoming', 'Будущие'),
            ('today', 'Сегодня'),
            ('overdue', 'Просроченные'),
            ('posted', 'Опубликованные'),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        value = self.value()
        if value == 'upcoming':
            return queryset.filter(is_posted=False, scheduled_time__gte=now)
        if value == 'today':
            local_today = timezone.localtime(now).date()
            return queryset.filter(scheduled_time__date=local_today)
        if value == 'overdue':
            return queryset.filter(is_posted=False, scheduled_time__lt=now - PUBLISH_GRACE)
        if value == 'posted':
            return queryset.filter(is_posted=True)
        return queryset


@admin.register(PostingSchedule)
class PostingScheduleAdmin(CityScopedAdmin, admin.ModelAdmin):
    list_display = ['post_title', 'scheduled_time', 'slot_state', 'theme', 'events_count',
                    'platform', 'status', 'post_link', 'post_preview']
    list_filter = [SlotFilter, 'platform', 'status']
    list_editable = ["scheduled_time", "status"]
    search_fields = ['generated_post__title', 'generated_post__content']
    date_hierarchy = 'scheduled_time'
    list_per_page = 25
    ordering = ['-scheduled_time']
    readonly_fields = ['posted_at', 'post_preview']
    exclude = ['created_at', 'updated_at']

    change_list_template = "content_generator/postingschedule_change_list.html"
    change_form_template = "content_generator/change_form_with_preview.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related('generated_post',
                            'generated_post__event_selection',
                            'generated_post__event_selection__filter_set')
            .annotate(events_n=Count('generated_post__event_selection__selected_events',
                                     distinct=True))
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['slot_summary'] = self._slot_summary(request)
        return super().changelist_view(request, extra_context=extra_context)

    def _slot_summary(self, request):
        """Counters for the toolbar — one aggregate query, each links to a filter."""
        now = timezone.now()
        counts = self.scope_by_city(request, PostingSchedule.objects.all()).aggregate(
            all=Count('id'),
            upcoming=Count('id', filter=Q(is_posted=False, scheduled_time__gte=now)),
            overdue=Count('id', filter=Q(is_posted=False,
                                         scheduled_time__lt=now - PUBLISH_GRACE)),
            posted=Count('id', filter=Q(is_posted=True)),
        )
        base_url = reverse('admin:content_generator_postingschedule_changelist')
        rows = [
            ('all', 'Все', counts['all'], '#2c3e50'),
            ('upcoming', 'Будущие', counts['upcoming'], '#2f7d32'),
            ('overdue', 'Просроченные', counts['overdue'], '#ba2121'),
            ('posted', 'Опубликованные', counts['posted'], '#666'),
        ]
        active = request.GET.get(SlotFilter.parameter_name, 'all')
        return [{
            'key': key,
            'label': label,
            'count': count,
            'color': css_color(color),
            'active': key == active,
            'url': base_url if key == 'all' else f'{base_url}?{SlotFilter.parameter_name}={key}',
        } for key, label, count, color in rows]

    @admin.display(description='Пост', ordering='generated_post__title')
    def post_title(self, obj):
        post = obj.generated_post
        if post is None:
            return '—'
        if post.image:
            return format_html('{}<div class="dsn-slot-note">🖼 с картинкой</div>', post.title)
        return post.title

    @admin.display(description='Текст')
    def post_link(self, obj):
        if obj.generated_post_id is None:
            return '—'
        url = reverse('admin:content_generator_generatedpost_change',
                      args=[obj.generated_post_id])
        return format_html('<a href="{}">✎ править</a>', url)

    @admin.display(description='Тема')
    def theme(self, obj):
        selection = getattr(obj.generated_post, 'event_selection', None)
        if selection is None:
            return '—'
        if selection.filter_set_id:
            return selection.filter_set.name
        return selection.name

    @admin.display(description='Событий', ordering='events_n')
    def events_count(self, obj):
        return getattr(obj, 'events_n', 0) or '—'

    @admin.display(description='Слот')
    def slot_state(self, obj):
        """Whether the slot is still going to fire — a missed one is silent otherwise."""
        if obj.is_posted or obj.status == 'Posted':
            posted = timezone.localtime(obj.posted_at).strftime('%d.%m %H:%M') if obj.posted_at else ''
            return format_html('<span style="color:{};">опубликован</span>{}', css_color('#2f7d32'),
                               format_html('<div class="dsn-slot-note">{}</div>', posted) if posted else '')
        if obj.scheduled_time is None:
            return '—'
        if obj.status != 'ReadyToPost':
            return obj.get_status_display()

        left = obj.scheduled_time - timezone.now()
        if -PUBLISH_GRACE <= left <= timedelta(0):
            return format_html('<span style="color:{};">публикуется</span>', css_color('#b36b00'))
        if left < -PUBLISH_GRACE:
            return format_html(
                '<span style="color:{};" title="Слот пропущен, пост не будет '
                'опубликован — поставьте новое время">просрочен на {}</span>',
                css_color('#ba2121'), _human_delta(left),
            )
        return format_html('<span style="color:{};">через {}</span>', css_color('#555'), _human_delta(left))

    @admin.display(description='Пост в канале')
    def post_preview(self, obj):
        if obj is None or obj.generated_post_id is None:
            return '—'
        card = obj.generated_post.markdown_post_view_model()
        return format_html(
            '<div class="tg-post-cell">{}'
            '<button type="button" class="tg-post-toggle">Развернуть</button></div>',
            card,
        )


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
            city_id=selection.city_id,
            event_selection=selection,
            post_template=template,
            title=f"Подборка: {selection.name}",
            content=content,
            status='draft',
            generated_by=request.user
        )
    messages.success(request, "Посты успешно сгенерированы!")


@admin.register(EventSelection)
class EventSelectionAdmin(CityScopedAdmin, admin.ModelAdmin):
    list_display = ['name', 'filter_set', 'status', 'created_by', 'created_at']
    list_filter = ['status', 'created_at']
    exclude = ['created_at']
    search_fields = ['name']
    filter_horizontal = ['selected_events']
    actions = [generate_post_action, 'generate_post_api']

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['wizard_url'] = reverse('content_generator_wizard')
        return super().changelist_view(request, extra_context=extra_context)

    change_list_template = "content_generator/eventselection_change_list.html"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user

        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        obj = form.instance
        if obj.filter_set:
            existing_events = set(obj.selected_events.all())
            filtered_events = FilterService.apply_filters(obj.filter_set, city=obj.city_id)
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