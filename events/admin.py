from django.contrib import admin, messages
from django.utils.translation import ngettext
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils import timezone

import markdown

from .models import EventsNotApprovedNew, EventsNotApprovedProposed, Events2Post, PostingTime, Parameter, Event


from . import utils
from django import forms
from .widgets import PlaceAutocompleteWidget


def open_url(obj):
    return format_html("<a href='%s' target='_blank'>%s</a>" % (obj.url, obj.url))


open_url.short_description = "URL"


class FromDateFilter(admin.SimpleListFilter):
    title = 'Event Date Filter'
    parameter_name = 'from_date_field'

    def lookups(self, request, model_admin):
        return [
            ('date_from_tomorrow', 'Tomorrow'),
            ('date_from_tmrw_until_end', 'Tomorrow – End Week'),
            ('date_from_3days', '3 days ahead'),
            ('date_from_week', 'A week ahead'),
            ('date_from_next_week', 'Next week (Mon-Sun)'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'date_from_tomorrow':
            return queryset.filter(from_date__gte=(timezone.now() + timezone.timedelta(days=1)))
        if self.value() == 'date_from_tmrw_until_end':
            monday = timezone.now() + timezone.timedelta(days=(7 - timezone.now().weekday()))
            return queryset.filter(from_date__gte=(timezone.now() + timezone.timedelta(days=1))).filter(from_date__lt=monday)
        if self.value() == 'date_from_3days':
            return queryset.filter(from_date__gte=(timezone.now() + timezone.timedelta(days=3)))
        if self.value() == 'date_from_week':
            return queryset.filter(from_date__gte=(timezone.now() + timezone.timedelta(days=7)))
        if self.value() == 'date_from_next_week':
            monday = timezone.now() + timezone.timedelta(days=(7 - timezone.now().weekday()))
            sunday = monday + timezone.timedelta(days=6)
            return queryset.filter(from_date__gte=monday).filter(from_date__lt=sunday)
        return queryset


class EventsAdmin(admin.ModelAdmin):
    change_list_template = "events/change_list_not_approved.html"

    list_display = ["title", "approved", "from_date_order", open_url, "was_old"]
    list_filter = [FromDateFilter, "explored_date"]
    search_fields = ["title", "post"]
    actions = ["approve_event", "moderate_events"]
    ordering = ["-explored_date", "-from_date"]
    readonly_fields = ('image_tag',)

    def approve_event(self, request, queryset):
        updated = queryset.update(approved=True)
        self.message_user(
            request,
            ngettext(
                "%d event was successfully approved.",
                "%d events were successfully approved.",
                updated,
            )
            % updated,
            messages.SUCCESS,
        )
        utils.move_event_to_post(self.model)

    def from_date_order(self, obj):
        return obj.from_date_color()

    from_date_order.admin_order_field = 'from_date'

    def moderate_events(self, request, queryset):
        ids = list(queryset.values_list('id', flat=True))
        answer = utils.moderate_not_approved_events(ids)
        if answer:
            self.message_user(
                request,
                ngettext(
                    "%d event was successfully added for moderation AI process.",
                    "%d events were successfully added for moderation AI process.",
                    len(ids),
                )
                % len(ids),
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                ngettext(
                    "%d event wasn't added for moderation AI process.",
                    "%d events weren't added for moderation AI process.",
                    len(ids),
                )
                % len(ids),
                messages.ERROR,
            )

    def image_tag(self, obj):
        if obj.image_upload:
            return format_html('<img src="{}" style="max-width: 200px; max-height: 200px;" />', obj.image_upload.url)
        return 'No Image'

    approve_event.short_description = "Mark selected stories as approved"


# Edited form
class Events2PostAdminForm(forms.ModelForm):
    class Meta:
        model = Events2Post
        widgets = {
            'address': PlaceAutocompleteWidget(),
        }
        fields = '__all__'


class Events2PostAdmin(admin.ModelAdmin):
    change_list_template = "events/change_list_approved.html"
    change_form_template = "events/change_form.html"

    class Media:
        js = ('admin_place_searching.js',)

    list_display = [
        "title",
        "queue",
        "post_date",
        "from_date_color",
        open_url,
        "status_color",
        # "post_check"
    ]

    list_editable = ["queue", "post_date"]
    search_fields = ["title", "post"]
    actions = [
        "change_status_to_ReadyToPost",
        "change_status_to_Spam",
        "change_status_to_Posted",
        "prepare_events",
        #"clear_post_time",
        "change_queue",
        #'update_post_text_for_posting',
        'transfer_events_to_site',
        utils.post_date_order_by_queue,
        #utils.refresh_posting_time,
        'text_post_check'
    ]
    admin.ModelAdmin.save_on_top = True
    admin.ModelAdmin.actions_on_bottom = True
    admin.ModelAdmin.actions_selection_counter = True

    readonly_fields = ("markdown_post_view_model",)
    exclude = ("queue", "explored_date", )

    exclude_posted = ("markdown_post_view_model", "image_upload",
                      "address", "place", "post_date", "is_ready")
    exclude_not_posted = ('post_url',)

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if obj and obj.status == 'Posted':
            for incl_field in self.exclude_not_posted:
                if incl_field not in fields:
                    fields.append(incl_field)
            fields = [field for field in fields if field not in self.exclude_posted]
        else:
            fields = [field for field in fields if field not in self.exclude_not_posted]

        return fields

    form = Events2PostAdminForm

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if 'object_id' in request.resolver_match.kwargs:
            return queryset
        if request.GET.get('all') == 'true':
            return queryset  # Show all events
        return queryset.exclude(status='Posted')

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_all_url'] = self.get_show_all_url(request)
        extra_context['filter_ready_to_post_url'] = self.get_filter_ready_to_post_url(request)
        return super().changelist_view(request, extra_context=extra_context)

    def get_show_all_url(self, request):
        from django.urls import reverse

        opts = self.model._meta
        base_url = reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
        query_params = request.GET.copy()
        query_params['all'] = 'true'
        query_string = urlencode(query_params, doseq=True)
        return f'{base_url}?{query_string}'

    def get_filter_ready_to_post_url(self, request):
        from django.urls import reverse

        opts = self.model._meta
        base_url = reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')
        query_params = request.GET.copy()
        query_params['status__exact'] = 'ReadyToPost'
        query_string = urlencode(query_params, doseq=True)
        return f'{base_url}?{query_string}'

    def markdown_post_view(self, instance):
        html_image = f"<div style='width:325px;'><img src='{instance.image}' width='325px'>"
        html_post = markdown.markdown(instance.post
                                      .replace('*','**')
                                      .replace("\n", "<br>")
                                      .replace('_','*')
                                      )
        return format_html(html_image+html_post + '</div>')

    def get_ordering(self, request):
        return ["status", "queue"]


    def change_status_to_ReadyToPost(self, request, queryset):
        updated = queryset.update(status="ReadyToPost")
        self.message_user(
            request,
            ngettext(
                "%d event was changed on ReadyToPost.",
                "%d events were changed on ReadyToPost.",
                updated,
            )
            % updated,
            messages.SUCCESS,
        )

    def change_status_to_Spam(self, request, queryset):
        updated = queryset.update(status="Spam")
        self.message_user(
            request,
            ngettext(
                "%d event was changed on Spam.",
                "%d events were changed on Spam.",
                updated,
            )
            % updated,
            messages.SUCCESS,
        )

    def change_status_to_Posted(self, request, queryset):
        updated = queryset.update(status="Posted")
        self.message_user(
            request,
            ngettext(
                "%d event was changed on Posted.",
                "%d events were changed on Posted.",
                updated,
            )
            % updated,
            messages.SUCCESS,
        )

    utils.post_date_order_by_queue.acts_on_all = True

    # empty post_time
    def clear_post_time(self, request, queryset):
        queryset.update(post_date=None)

    # Change queue of events by round (1->2, 2->3, 3->1)
    def change_queue(self, request, queryset):
        len_que = len(queryset)
        for i in range(len_que):
            u = i + 1
            if i == (len_que - 1):
                u = 0
            queryset.filter(event_id=queryset[i].event_id).update(
                queue=queryset[u].queue
            )
        utils.post_date_order_by_queue(self, request, queryset)

    change_queue.short_description = "Change event place"

    def update_post_text_for_posting(self, request, queryset):
        events = queryset.all()

        for event in events:
            event.remake_post(save=True)


    def transfer_events_to_site(self, request, queryset):
        updated = utils.move_event_to_site(self.model)
        self.message_user(
            request,
            ngettext(
                "%d event was successfully transfered to site version.",
                "%d events were successfully transfered to site version.",
                updated,
            )
            % updated,
            messages.SUCCESS,
        )

    def text_post_check(self, request, queryset):
        text = '%d events:'
        updated = queryset.count()
        for obj in queryset:
            check_result = obj.post_check()
            if check_result:
                text += f" {obj.title} – {obj.post_check()};"
            else:
                updated = updated-1

        self.message_user(
            request,
            ngettext(
                text,
                text,
                updated
            )
            % updated,
        )


    def prepare_events(self, request, queryset):
        ids = list(queryset.values_list('id', flat=True))
        answer = utils.prepare_events(ids)
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


weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class PostingTimesAdmin(admin.ModelAdmin):

    list_filter = ["start_weekday"]
    ordering = ["start_weekday", "posting_time_hours"]
    list_editable = ["posting_time",]

    def weekdays(self):
        if (0 <= self.start_weekday < 7) & (0 <= self.end_weekday < 7):
            return f"{weekdays[self.start_weekday]}-{weekdays[self.end_weekday]}"
        if self.start_weekday < 0:  # we can add special postingtime for special date
            return f"day – {self.start_weekday*-1}"

    def timepost(self):
        return f"{self.posting_time_hours}:{self.posting_time_minutes:02}"

    list_display = [weekdays, timepost, "posting_time", ]


class ParametersAdmin(admin.ModelAdmin):
    list_display = ['site', 'parameter_name', 'value', 'commentary']
    list_editable = ['value', 'commentary']
    actions = ["copy",]
    change_list_template = "events/param_change_list.html"

    def copy(self, request, queryset):
        for obj in queryset:
            obj.id = None
            obj.save()
    copy.short_description = "Duplicate selected record"


admin.site.register(EventsNotApprovedNew, EventsAdmin)
admin.site.register(EventsNotApprovedProposed, EventsAdmin)
admin.site.register(PostingTime, PostingTimesAdmin)
admin.site.register(Events2Post, Events2PostAdmin)
admin.site.register(Parameter, ParametersAdmin)
admin.site.register(Event)
