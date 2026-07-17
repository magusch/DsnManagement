import json

import markdown

from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.template import loader
from django.contrib import messages

from .models import EventsNotApprovedNew, EventsNotApprovedProposed, Events2Post, Parameter, Event

from . import utils

from .helper.open_ai_helper import OpenAIHelper
import threading
from django.db import close_old_connections
from types import SimpleNamespace


def _run_in_background(target, *args, **kwargs):
    def _wrapper():
        try:
            close_old_connections()
            target(*args, **kwargs)
        finally:
            close_old_connections()
    threading.Thread(target=_wrapper, daemon=True).start()


def event_post_html(request, event_id):
    event = get_object_or_404(Events2Post, pk=event_id)
    # image = f"<img src='{event.image}'>"
    # html = image + markdown.markdown(event.post)
    return HttpResponse(event.markdown_post_view_model())


def all_events(request):
    all_events = Events2Post.objects.filter(status="Posted")
    template = loader.get_template('index.html')
    context = {
        'all_events': all_events,
    }
    return HttpResponse(template.render(context, request))


def event_list(request):
    events = Event.objects.all()
    template = loader.get_template('events/event_list.html')
    context = {
        'events': events
    }
    return HttpResponse(template.render(context, request))


def event_full(request, id):
    event = get_object_or_404(Event, pk=id)
    template = loader.get_template('events/event_full.html')
    context = {
        'event': event
    }
    return HttpResponse(template.render(context, request))


@staff_member_required
def check_event_status(request):
    return HttpResponse("Pass")

@staff_member_required
def count_events_by_day(request):
    answer = json.dumps(utils.count_events_by_day())
    return HttpResponse(answer)

@staff_member_required
def move_approved_events(request):
    def _do_move():
        utils.move_event_to_post(EventsNotApprovedNew)
        utils.move_event_to_post(EventsNotApprovedProposed)
    _run_in_background(_do_move)
    if 'HTTP_REFERER' in request.META:
        response = redirect(request.META['HTTP_REFERER'])
    else:
        response = HttpResponse('Ok')

    return response

@staff_member_required
def transfer_posted_events_to_site(request):
    _run_in_background(utils.move_event_to_site, Events2Post)
    if 'HTTP_REFERER' in request.META:
        response = redirect(request.META['HTTP_REFERER'])
    else:
        response = HttpResponse('Ok')

    return response


@staff_member_required
def remove_old_events(request):
    def _do_delete():
        utils.delete_old_events(EventsNotApprovedNew)
        utils.delete_old_events(EventsNotApprovedProposed)
        utils.delete_old_events(Events2Post)
    _run_in_background(_do_delete)
    if 'HTTP_REFERER' in request.META:
        response = redirect(request.META['HTTP_REFERER'])
    else:
        response = HttpResponse('Ok')
    return response


@csrf_exempt
@staff_member_required
def fill_empty_post_time(request):
    if request.method == "POST":
        response = None
        #utils.refresh_posting_time(request=request)

    elif request.method == "GET":
        # Collect IDs to avoid passing QuerySet across thread boundaries
        event_ids = list(
            Events2Post.objects.filter(status="ReadyToPost")
            .order_by("queue")
            .values_list("id", flat=True)
        )

        body_str = request.body.decode("utf-8", errors="ignore") if hasattr(request, "body") else ""

        def _do_refresh(ids, body):
            req = SimpleNamespace(body=body)
            qs = Events2Post.objects.filter(id__in=ids).order_by("queue")
            utils.refresh_posting_time(None, req, queryset=qs)

        _run_in_background(_do_refresh, event_ids, body_str)

        if 'HTTP_REFERER' in request.META:
            response = redirect(request.META['HTTP_REFERER'])
        else:
            response = HttpResponse('Ok')

    return response


@staff_member_required
def update_all(request):
    def _do_update_all():
        try:
            utils.move_event_to_post(EventsNotApprovedNew)
            utils.move_event_to_post(EventsNotApprovedProposed)

            ids = list(
                Events2Post.objects.filter(status="ReadyToPost")
                .order_by("queue")
                .values_list("id", flat=True)
            )
            req = SimpleNamespace(body="")
            qs = Events2Post.objects.filter(id__in=ids).order_by("queue")
            utils.refresh_posting_time(None, req, queryset=qs)

            utils.post_date_order_by_queue()
            utils.delete_old_events(EventsNotApprovedNew)
            utils.delete_old_events(EventsNotApprovedProposed)
            utils.delete_old_events(Events2Post)
            utils.move_event_to_site(Events2Post)
        finally:
            pass

    _run_in_background(_do_update_all)

    if 'HTTP_REFERER' in request.META:
        response = redirect(request.META['HTTP_REFERER'])
    else:
        response = HttpResponse('Ok')

    return response


@csrf_exempt
@staff_member_required
def get_parameters(request):
    if request.method == "GET":
        prms = Parameter.objects

        if 'site' in request.GET:
            prms = prms.filter(site=request.GET['site'])

        if 'name' in request.GET:
            prms = prms.filter(parameter_name=request.GET['name'])

        params_in_db = []
        for row in prms.values():
            params_in_db.append(row)
        return HttpResponse(json.dumps(params_in_db))

# From post text to html
@staff_member_required
def markdown_to_html(request):
    html = ''
    if request.method == "POST":
        if 'text' in request.POST:
            html = markdown.markdown(request.POST['text'])
    if request.method == "GET":
        if 'text' in request.GET:
            html = markdown.markdown(request.GET['text'])
    return HttpResponse(html)

@csrf_exempt
@staff_member_required
def remake_post(request, id=0, save=0):
    if request.method == "POST":
        event_dict = dict(request.POST)

        for k, v in event_dict.items():
            event_dict[k] = v[0]
        new_event = utils.make_a_post_text(event_dict, save)
        return HttpResponse(json.dumps(new_event))

    if request.method == "GET" and id != 0:
        if type(id) != int:
            ids = id.split(',')
            new_posts = []
            for id_ex in ids:
                event = get_object_or_404(Events2Post, pk=id_ex)
                new_event = utils.make_a_post_text(event, save)
                new_posts.append(new_event['post'])

            return HttpResponse(json.dumps(new_posts))
        else:
            event = get_object_or_404(Events2Post, pk=id)
            new_event = utils.make_a_post_text(event, save)
            new_post = new_event['post']
            return HttpResponse(json.dumps(new_post))

    return redirect(request.META['HTTP_REFERER'])

@csrf_exempt
@staff_member_required
def remake_post_ai(request, id=0, save=0):
    ai = OpenAIHelper()
    if request.method == "POST":
        event_dict = dict(request.POST)

        for k, v in event_dict.items():
            event_dict[k] = v[0]

        new_event_data = ai.new_event_data(event_dict)
        return HttpResponse(json.dumps([new_event_data]))

    if request.method == "GET" and id != 0:
        # if type(id) != int:
        #     ids = id.split(',')
        #     new_posts = []
        #     for id_ex in ids:
        #         event = get_object_or_404(Events2Post, pk=id_ex)
        #         new_posts.append(utils.make_a_post_text(event, save))
        #
        #     return HttpResponse(json.dumps(new_posts))
        # else:
        # new_post = utils.make_a_post_text(event, save)
        event = get_object_or_404(Events2Post, pk=id)

        new_event_data = ai.new_event_data(event.__dict__)

        return HttpResponse(json.dumps([new_event_data]))

    return redirect(request.META['HTTP_REFERER'])


@staff_member_required
def check_posts(request):
    ready_to_post_events = Events2Post.objects.filter(status="ReadyToPost").order_by("queue").all()
    result = []

    for event in ready_to_post_events:
        check_result = event.post_check()
        if check_result:
            result.append(
                {
                    'id': event.id,
                    'event_id': event.event_id,
                    'title': event.title,
                    'errors': event.post_check(),
                    'date_post': event.post_date.isoformat() if event.post_date else None
                }
            )

    answer = json.dumps(result, ensure_ascii=False)
    return HttpResponse(answer)


@csrf_exempt
@staff_member_required
def proxy_request_to_channel_api(request):
    if request.method == "POST":

        data = json.loads(request.body)
        response, error = utils.channel_api_request(data)

        if response:
            return JsonResponse(response.json(), status=response.status_code)
        else:
            return JsonResponse({"error": error}, status=502)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=405)


from django.shortcuts import render, redirect
from django.views import View
from .forms import EventAddForm


class EventAddView(View):
    form_class = EventAddForm
    template_name = 'add_event.html'

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = self.form_class(request.POST, request.FILES)
        today = timezone.now().date()
        events_today = EventsNotApprovedProposed.objects.filter(explored_date__date=today).count()
        if events_today >= 30:
            messages.error(request, 'Добавление мероприятий сегодня больше недоступно.')
            return redirect('add_event')

        if form.is_valid():
            event = form.save(commit=False)
            event.save()
            messages.success(request, 'Мероприятие успешно добавлено!')
            return redirect('add_event')
        return render(request, self.template_name, {'form': form})


class EventAddViewHtmx(View):
    form_class = EventAddForm
    template_name = 'add_event_htmx.html'

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = self.form_class(request.POST, request.FILES)
        today = timezone.now().date()
        events_today = EventsNotApprovedProposed.objects.filter(explored_date__date=today).count()
        if events_today >= 30:
            messages.error(request, 'Добавление мероприятий сегодня больше недоступно.')
            return redirect('add_event')

        if form.is_valid():
            event = form.save(commit=False)
            event.save()
            messages.success(request, 'Мероприятие успешно добавлено!')
            return JsonResponse({
                'success': True,
                'message': 'Мероприятие успешно добавлено json!'
            })
            return redirect('add_event')
        return render(request, self.template_name, {'form': form})

