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

_FREE_KEYWORDS = ('бесплатно', 'free', 'вход свободный', 'свободный вход', 'бесплатный')


def parse_price_int(price_text):
    """Parse integer price from price text.

    Returns:
        int: price number (e.g. 300), 0 if free, or None if can't parse.
    """
    if not price_text:
        return None
    text = price_text.strip().lower()
    if any(kw in text for kw in _FREE_KEYWORDS):
        return 0
    numbers = re.findall(r'\d+', text.replace(' ', ''))
    if numbers:
        return int(numbers[0])
    return None

current_tz = timezone.get_current_timezone()

current_tz_int = timezone.now().astimezone(current_tz).hour - timezone.now().hour

if current_tz_int < 0:
    current_tz_int = 24 + current_tz_int

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
    try:
        body = request.body.decode('utf-8') if isinstance(request.body, bytes) else request.body
        last_date = datetime.datetime.fromisoformat(body.strip())
    except (ValueError, UnicodeDecodeError):
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
        last_queue_event = Events2Post.objects.order_by("-queue").first()
        last_queue = last_queue_event.queue if last_queue_event else 0
        try:
            post_time = good_post_time(last_post_event.post_date)
        except (AttributeError, ValueError, TypeError):
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
        "ticket_url",
        "price",
        "price_int",
        "category",
        "address",
        "explored_date",
        "from_date",
        "to_date",
        "source"
    ]

    events = Events_model.objects.filter(approved=True)

    post_date, queue = last_post_date()

    for event in events:
        event_dict = model_to_dict(event, fields=event2post_list)
        # make post in transfering
        event_dict['prepared_text'] = event_dict['post']
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
    if Events_model == Events2Post:
        return
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
        price_text = event.price
    elif type(event) == dict:
        post_helper = PostHelper(event)
        remake_event_data['post'] = post_helper.post_markdown()
        remake_event_data['place'] = post_helper.place_id()
        main_category = post_helper.main_category()
        if main_category is not None:
            remake_event_data['main_category'] = main_category
        price_text = event.get('price', '')
    else:
        price_text = ''

    price_int = parse_price_int(price_text)
    if price_int is not None:
        remake_event_data['price_int'] = price_int

    return remake_event_data


def channel_api_request(data):
    url = CHANNEL_API_URL + data['api_url']
    headers = {
        'Authorization': f"Bearer {CHANNEL_API_TOKEN}",
    }
    method = data.get('method', 'GET').upper()

    try:
        if method == 'POST':
            response = requests.post(url, headers=headers, json=data.get('data'), timeout=30)
        else:
            response = requests.get(url, headers=headers, timeout=30)
    except requests.RequestException as e:
        return None, str(e)

    if response.status_code != 200:
        try:
            detail = response.json().get('detail', response.text)
        except Exception:
            detail = response.text
        return response, f"HTTP {response.status_code}: {detail}"

    return response, None


def _api_call(data):
    """Common wrapper: returns (success, error_message)."""
    response, error = channel_api_request(data)
    if error:
        return False, error
    return True, None


def moderate_not_approved_events(event_ids):
    return _api_call({
        "api_url": "api/ai_moderate_not_approved_events",
        "method": "POST",
        "data": {"ids": event_ids}
    })


def prepare_events(event_ids):
    return _api_call({
        "api_url": "api/prepare_events",
        "method": "POST",
        "data": {"ids": event_ids}
    })


def upload_image_event_to_s3(event_ids):
    return _api_call({
        "api_url": "api/upload_event_images_to_s3/",
        "method": "POST",
        "data": {"event_ids": event_ids}
    })


def recalculate_scores(event_ids, table):
    return _api_call({
        "api_url": "api/tasks/recalculate-scores/",
        "method": "POST",
        "data": {"table": table, "ids": event_ids, "force": True}
    })