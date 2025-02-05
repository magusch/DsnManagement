import os, json
import datetime, re
import requests

from typing import Generator, List

from django.utils import timezone
from django.forms.models import model_to_dict

from .models import Events2Post, PostingTime, Event

from .helper.post_helper import PostHelper


CHANNEL_API_URL = os.environ.get("CHANNEL_API_URL")
CHANNEL_API_TOKEN = os.environ.get("CHANNEL_API_TOKEN")

current_tz = timezone.get_current_timezone()

current_tz_int = (
    timezone.get_default_timezone().normalize(timezone.now()).hour - timezone.now().hour
)
if current_tz_int<0: current_tz_int=24+current_tz_int

def _is_weekday(dt: datetime.datetime) -> bool:
    return dt.weekday() in [0, 1, 2, 3, 4]


def _days_posting_times(time_point: datetime) -> Generator[None, List[datetime.datetime], None]:
    weekday = (
        PostingTime.objects.filter(start_weekday__lte=0)
        .filter(end_weekday__gte=4)
        .order_by("posting_time__hour")
        .first()
    )
    weekend = (
        PostingTime.objects.filter(start_weekday__lte=5)
        .filter(end_weekday__gte=6)
        .order_by("posting_time__hour")
        .first()
    )

    today_posting_times = weekday if _is_weekday(time_point) else weekend
    posting_times = [i for i in today_posting_times if i >= time_point]

    if posting_times:
        yield posting_times

    while True:
        time_point += datetime.timedelta(days=1)

        ymd = dict(
            year=time_point.year,
            month=time_point.month,
            day=time_point.day,
        )

        datetimes = weekday if _is_weekday(time_point) else weekend
        yield [i.replace(**ymd) for i in datetimes]


def _postin_times(target_time: datetime=None):
    if target_time is None:
        target_time = timezone.now()

    times = _days_posting_times(target_time)

    while True:
        yield from next(times)


def refresh_posting_time(self, request, queryset):
    """
    Parameters
    ----------
    queryset : list
        список с записями в таблице.
    """
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', str(request.body)): #'yyyy-mm-ddThh:mm'
        last_date = datetime.fromisoformat(str(request.body))
    else:
        last_date = None

    times = _postin_times(last_date)

    for event in queryset:
        # if event.post_date is None:
        #     pass
        #
        # else:
        #     pass

        last_post = (
            Events2Post.objects.filter(status="ReadyToPost")
            .filter(queue__lt=event.queue)
            .order_by("-post_date")
            .first()
        )
        if not last_post or not last_post.post_date:
            last_post_time = timezone.now()
        else:
            last_post_time = last_post.post_date

        post_time = good_post_time(last_post_time)
        event.post_date = post_time
        event.save()


# Order by queue and change post_time in this order
def post_date_order_by_queue(*kwargs):
    query_post_date_ordered = Events2Post.objects.filter(status="ReadyToPost").order_by(
        "post_date"
    )
    query_post_date_ordered_list = [pd.post_date for pd in query_post_date_ordered]
    query_queue_ordered = Events2Post.objects.filter(status="ReadyToPost").order_by("queue")
    for i, event in enumerate(query_queue_ordered):

        event.post_date = query_post_date_ordered_list[0]
        query_post_date_ordered_list.pop(0)
        event.save()


def last_post_date():
    last_post_event = (
        Events2Post.objects.filter(status="ReadyToPost").filter(post_date__isnull=False).order_by("-post_date").first()
    )
    if last_post_event:
        last_queue = Events2Post.objects.order_by("-queue").first().queue
        try:
            post_time = good_post_time(current_tz.normalize(last_post_event.post_date))
        except:
            post_time = good_post_time(timezone.now())
        return post_time, last_queue + 2

    post_time = empty_queryset()
    return post_time, 1


# Move Events form not approved table to table with approved Events2Post
def move_event_to_post(Events_model):
    event2post_list = [
        "event_id",
        "title",
        "post",
        "full_text",
        "image",
        "url",
        "price",
        "category",
        "address",
        "explored_date",
        "from_date",
        "to_date",
    ]

    events = Events_model.objects.filter(approved=True)

    post_date, queue = last_post_date()

    for event in events:
        event_dict = model_to_dict(event, fields=event2post_list)
        # make post in transfering
        ev = make_a_post_text(event_dict)
        event_dict['post'] = ev['post']
        event_dict['place_id'] = ev['place'] if ev['place'] is not None else (event.place.id if event.place is not None else None)
        if 'main_category' in ev:
            event_dict['main_category'] = ev['main_category']

        Events2Post.objects.create(
            status="ReadyToPost", post_date=post_date, queue=queue, **event_dict
        )
        post_date, queue = last_post_date()

    events.delete()


def move_event_to_site(events_model):
    event2post_list = [
        "event_id",
        "title",
        "post",
        "full_text",
        "image",
        "url",
        "price",
        "category",
        "address",
        "place",
        "from_date",
        "to_date",
        "post_url"
    ]

    existed_site_events = Event.objects.values("event_id")
    events = events_model.objects.filter(status="Posted").exclude(event_id__in=existed_site_events)
    pub_datetime = timezone.now()
    event_count = events.count()
    for event in events:
        event_dict = {field: getattr(event, field) for field in event2post_list}

        if event.place is not None:
            event_dict['place'] = event.place
        else:
            event_dict['place'] = None

        Event.objects.create(
            pub_datetime=pub_datetime, **event_dict
        )

    return event_count


def good_post_time(last_post_time):
    if last_post_time <= timezone.now():
        last_post_time = timezone.now()
    post_time_query_first = (
        PostingTime.objects.filter(start_weekday__lte=last_post_time.weekday())
        .filter(end_weekday__gte=last_post_time.weekday())
        .filter(posting_time__hour__gte=last_post_time.hour + current_tz_int + 1)
        .order_by('posting_time__hour').first()
    )
    if post_time_query_first:
        post_time = last_post_time.replace(
            hour=post_time_query_first.posting_time.hour - current_tz_int,
            minute=post_time_query_first.posting_time.minute,
            second=0,
            microsecond=0,
        )
    else:
        next_day = last_post_time + timezone.timedelta(days=1)
        post_time = (
            PostingTime.objects.filter(start_weekday__lte=next_day.weekday())
            .filter(end_weekday__gte=next_day.weekday())
            .order_by("posting_time__hour")
            .first()
        )
        post_time = next_day.replace(
            hour=post_time.posting_time.hour - current_tz_int,
            minute=post_time.posting_time.minute,
            second=0,
            microsecond=0,
        )
    return post_time


# take posting time for last event


def empty_queryset():
    today = timezone.now() + timezone.timedelta(days=1)
    post_time = (
        PostingTime.objects.filter(start_weekday__lte=today.weekday())
        .filter(end_weekday__gte=today.weekday())
        .order_by("posting_time_hours")
        .first()
    )
    post_time = today.replace(
        hour=post_time.posting_time_hours,
        minute=post_time.posting_time_minutes,
        second=0,
        microsecond=0,
    )
    return post_time


def delete_old_events(Events_model):
    today = timezone.now()
    Events_model.objects.filter(to_date__lt=today).delete()


def count_events_by_day(*kwargs):
    query_post_date_ordered = Events2Post.objects.filter(status="ReadyToPost").order_by(
        "queue"
    )
    check_day = timezone.now().date()

    i=0
    posts_in_day = {}
    for pd in query_post_date_ordered:
        if pd.post_date.date()!=check_day:
            posts_in_day[check_day.day] = i
            if pd.post_date.date() == (check_day + timezone.timedelta(days=1)):
                check_day = check_day + timezone.timedelta(days=1)
            elif pd.post_date.date() != (check_day + timezone.timedelta(days=1)):
                if 'wrong_queue' in posts_in_day:
                    posts_in_day['wrong_queue'] += ", " + str(pd.queue)
                else:
                    posts_in_day['wrong_queue'] = str(pd.queue)
            i = 0
        i += 1
    posts_in_day[check_day.day] = i
    return posts_in_day


def make_a_post_text(event, save=0):
    remake_event_data = {}
    if type(event) == Events2Post:
        remaked_event = event.remake_post(save=save)
        remake_event_data['post'] = remaked_event['post']
        remake_event_data['place'] = remaked_event['place_id']
        remake_event_data['main_category'] = remaked_event['main_category']
    elif type(event) == dict:
        post_helper = PostHelper(event)
        remake_event_data['post'] = post_helper.post_markdown()
        remake_event_data['place'] = post_helper.place_id()
        main_category = post_helper.main_category()
        if main_category is not None:
            remake_event_data['main_category'] = main_category
    
    return remake_event_data


def channel_api_request(data):
    url = CHANNEL_API_URL + data['api_url']
    headers = {
        'Authorization': f"Bearer {CHANNEL_API_TOKEN}",
        'Content-Type': 'application/json'
    }

    if data['method'] == 'POST':
        response = requests.post(url, headers=headers, data=json.dumps(data['data']))
    elif data['method'] == 'GET':
        response = requests.get(url, headers=headers)
    else:
        response = requests.get(url, headers=headers)

    return response
