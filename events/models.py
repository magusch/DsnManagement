import re

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from pgvector.django import VectorField, HnswIndex

import random


from place.models import Place
from category.models import SubCategory, Category

from .helper.post_helper import PostHelper
from .helper.post_checker import PostChecker


def random_event_id():
    return f"event{random.randint(1, 99)}_{timezone.now().date()}"


monthes = ['января', 'февраля', "марта", "апреля",
           "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря"]


def default_post_text():
    month = monthes[default_event_date().month - 1]
    return f"* {month}*  фестиваль *«ФЕЙСТНЕЙМ»*\n\nТЕКСТ\n\n*Где:*\n*Когда:*\n*Вход:*\n"


def default_event_date():
    return timezone.now().replace(minute=0) + timezone.timedelta(days=3)

class Status(models.TextChoices):
    NEW = 'new', 'New'
    EXTRACTED = 'extracted', 'Extracted'
    NOT_EVENT = 'not_event', 'Not Event'
    PENDING = 'pending', 'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    SPAM = 'spam', 'Spam'
    DUPLICATE = 'duplicate', 'Duplicate'

    @property
    def color(self):
        colors = {
            Status.NEW: '#007bff',
            Status.EXTRACTED: '#17a2b8',
            Status.PENDING: 'orange',
            Status.APPROVED: 'green',
            Status.REJECTED: 'red',
            Status.SPAM: 'red',
            Status.DUPLICATE: 'gray',
            Status.NOT_EVENT: 'black',
        }
        return colors.get(self, 'black')  # 'black' как фолбек


class Source(models.TextChoices):
    TIMEPAD = 'TIMEPAD', 'Timepad'
    RADARIO = 'RADARIO', 'Radario'
    TICKETSCLOUD = 'TC', 'Ticketscloud'
    QTICKETS = 'QT', 'QTickets'
    CULTURE = 'CLTR', 'Culture'
    MTS = 'MTS', 'MTS'
    VK = 'VK', 'VK'
    TG = 'TG', 'Telegram'
    AI = 'AI', 'AI'
    OTHER = 'OTHER', 'Other'


class EventsNotApprovedNew(models.Model):
    event_id = models.CharField(max_length=30)
    approved = models.BooleanField(default=False, blank=True) # Deprecated
    title = models.CharField(max_length=500)
    status = models.CharField(
        max_length=30,
        choices=Status.choices, default=Status.NEW,
        db_index=True, null=True
    )
    post = models.TextField(default="", blank=True)
    full_text = models.TextField(default="", blank=True, null=True)
    image = models.CharField(max_length=500, blank=True, null=True)
    url = models.CharField(max_length=500, blank=True)
    ticket_url = models.CharField(max_length=500, blank=True, null=True)
    price = models.CharField(max_length=500, blank=True)
    price_int = models.IntegerField(null=True, blank=True)
    category = models.CharField(max_length=500, null=True, blank=True)
    address = models.CharField(max_length=500, blank=True)
    place = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.OTHER,
        db_index=True
    )
    explored_date = models.DateTimeField("published date and time", default=timezone.now)
    from_date = models.DateTimeField("event date_from", null=True, blank=True, default=default_event_date)
    to_date = models.DateTimeField(
        "event to_date",
        null=True, blank=True, default=default_event_date
    )
    score = models.IntegerField(verbose_name='total event score', null=True, blank=True)
    score_breakdown = models.JSONField(verbose_name='event score by categories',null=True, blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    embedding_model = models.CharField(max_length=64, null=True, blank=True)
    embedding_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            HnswIndex(
                name="enapproved_new_emb_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
                condition=Q(embedding__isnull=False),
            ),
        ]

    def __str__(self):
        return self.title

    def was_old(self):
        return self.explored_date <= timezone.now() - timezone.timedelta(days=2)

    def from_date_color(self):
        if (self.from_date - timezone.now()).days < 3:
            return format_html(
                f'<span style="color: Orange;">{self.from_date.ctime()}</span>'
            )
        else:
            return format_html(
                f'<span style="color: Green;">{self.from_date.ctime()}</span>'
            )

    def status_color(self):
        if self.status:
            status_enum = Status(self.status)
            return format_html(
            '<span style="color: {};">{}</span>',
                status_enum.color, status_enum.label
            )
        else:
            return self.status
    status_color.short_description = 'Status'


class EventsNotApprovedProposed(models.Model):
    event_id = models.CharField(max_length=30, default=random_event_id)
    approved = models.BooleanField(default=False) # Deprecated
    title = models.CharField("Заголовок", max_length=500)
    status = models.CharField(
        max_length=30,
        choices=Status.choices, default=Status.NEW,
        db_index=True, null=True
    )
    post = models.TextField(default="", blank=True)
    full_text = models.TextField("Текст мероприятия", default="", blank=True, null=True)
    image_upload = models.ImageField(upload_to='event_images/', blank=True, null=True)
    image = models.CharField("Ссылка на изображение", max_length=500, blank=True, null=True)
    url = models.CharField("Ссылка на мероприятие", max_length=500, blank=True)
    ticket_url = models.CharField(max_length=500, blank=True, null=True)
    price = models.CharField("Цена", default="1000₽", max_length=500, blank=True)
    price_int = models.IntegerField(null=True, blank=True)
    category = models.CharField("Категория (тип мероприятия)", max_length=500, null=True, blank=True)
    address = models.CharField("Адрес", max_length=500, blank=True)
    place = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.OTHER,
        db_index=True
    )
    explored_date = models.DateTimeField(
        "published date and time", default=timezone.now
    )
    from_date = models.DateTimeField(
        "Дата и время начала мероприятия",
        null=True, blank=True, default=default_event_date
    )
    to_date = models.DateTimeField(
        "Дата и время окончания мероприятия",
        null=True, blank=True, default=default_event_date
    )
    score = models.IntegerField(verbose_name='total event score', null=True, blank=True)
    score_breakdown = models.JSONField(verbose_name='event score by categories', null=True, blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    embedding_model = models.CharField(max_length=64, null=True, blank=True)
    embedding_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            HnswIndex(
                name="enapproved_prop_emb_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
                condition=Q(embedding__isnull=False),
            ),
        ]

    def __str__(self):
        return self.title

    def was_old(self):
        return self.to_date <= timezone.now()

    def from_date_color(self):
        if (self.from_date - timezone.now()).days < 2:
            return format_html(
                f'<span style="color: Orange;">{self.from_date.ctime()}</span>'
            )
        else:
            return format_html(
                f'<span style="color: Green;">{self.from_date.ctime()}</span>'
            )

    def save(self, *args, **kwargs):
        super(EventsNotApprovedProposed, self).save(*args, **kwargs)
        if self.image_upload and self.image != self.image_upload.url:
            self.image = self.image_upload.url
            super(EventsNotApprovedProposed, self).save(update_fields=['image'])


status_color = {"ReadyToPost": "green", "Posted": "red", "ForFuture": 'blue', "Spam": "red", "Scrape": "purple",
                "Error": "orange", "Rejected": "red", "Expired": "gray", "OnlyApi": "purple"}


def last_queue():
    q = Events2Post.objects.order_by("-queue").first()
    if q:
        return q.queue + 2
    else:
        return 1


class Events2Post(models.Model):  # Table events for posting
    event_id = models.CharField(max_length=30, default=random_event_id, db_index=True)
    queue = models.IntegerField(default=last_queue)
    is_ready = models.BooleanField(default=False)
    title = models.CharField(default="фестиваль *«ФЕЙСТНЕЙМ»", max_length=500)
    post = models.TextField(default=default_post_text, blank=True)
    prepared_text = models.TextField(default="", blank=True, null=True)
    full_text = models.TextField(default="", blank=True, null=True)
    image = models.CharField(max_length=500, blank=True, null=True)
    image_upload = models.ImageField(upload_to='event_images/', blank=True, null=True)
    url = models.CharField(max_length=500, blank=True)
    ticket_url = models.CharField(max_length=500, blank=True, null=True)
    status = models.CharField(
        max_length=15,
        choices=(("ReadyToPost", "Ready To Post"), ("Posted", "Posted"), ("ForFuture", "For Future"), ("OnlyApi", "OnlyApi"),
                 ("Spam", "Spam"), ("Scrape", "Scrape It"), ("Error", "Error"), ("Rejected", "Rejected"), ("Expired", "Expired"),),
        default="ReadyToPost",
        db_index=True
    )
    price = models.CharField(max_length=150, blank=True)
    price_int = models.IntegerField(null=True, blank=True)
    category = models.CharField(max_length=500, null=True, blank=True)

    main_category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True)
    address = models.CharField(max_length=500, blank=True)

    place = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.OTHER,
        db_index=True
    )
    explored_date = models.DateTimeField(
        "published date and time", default=timezone.now
    )
    post_date = models.DateTimeField("datetime for posting", blank=True, null=True)
    from_date = models.DateTimeField(
        "event from_date", default=default_event_date
    )
    to_date = models.DateTimeField(
        "event to_date", default=default_event_date
    )
    post_url = models.CharField(max_length=500, blank=True, null=True)
    score = models.IntegerField(verbose_name='total event score', null=True, blank=True)
    score_breakdown = models.JSONField(verbose_name='event score by categories', null=True, blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    embedding_model = models.CharField(max_length=64, null=True, blank=True)
    embedding_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            HnswIndex(
                name="events2post_emb_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
                condition=Q(embedding__isnull=False),
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.category is not None and (not self.main_category_id or self.main_category_id == 2):
            subcategory, created = SubCategory.objects.get_or_create(name=self.category)
            self.main_category = subcategory.category
        if self.image_upload and self.image != self.image_upload.url:
            self.image = self.image_upload.url
        super(Events2Post, self).save(*args, **kwargs)

    def to_delete(self):
        return self.explored_date <= timezone.now() - timezone.timedelta(days=2)

    def status_color(self):
        return format_html(
            f'<span style="color: {status_color[self.status]};">{self.status}</span>'
        )

    def from_date_color(self):
        #from_date_color_html = ""
        if self.status == 'Error':
            from_date_color_html = f'<span style="color: Red;">{self.from_date.ctime()}</span>'
        elif self.status == 'Rejected':
            from_date_color_html = f'<span style="color: Gray;">{self.from_date.ctime()}</span>'
        elif self.status == 'ForFuture':
            from_date_color_html = f'<span style="color: Blue;">{self.from_date.ctime()}</span>'
        elif self.status == 'Posted' or self.status == 'Spam' or self.from_date < timezone.now():
            from_date_color_html = f'<span style="color: Red;">{self.from_date.ctime()}</span>'
        elif self.status == 'Scrape':
            from_date_color_html = f'<span style="color: Purple;">{self.from_date.ctime()}</span>'
        elif (self.from_date - timezone.now()).days < 3:
            from_date_color_html = f'<span style="color: Orange;">{self.from_date.ctime()}</span>'
        else:
            from_date_color_html = f'<span style="color: Green;">{self.from_date.ctime()}</span>'

        if self.is_ready is True:
            from_date_color_html += "<div style='text-align:left'>✅</div>"

        return format_html(from_date_color_html)

    def markdown_post_view_model(self):
        from events.helper.markdown_v2 import v2_to_html
        html_image = f"<div id='markdown_post' style='width:325px;'><img src='{self.image}' width='325px'>"
        html_post = v2_to_html(self.post)
        return format_html(html_image + html_post + '</div>')

    def address_markdown(self):
        return self.place.markdown_address()

    def remake_post(self, save=False):
        post_helper = PostHelper(self)

        new_maked_event = {
            'post': post_helper.post_markdown(),
            'place_id': post_helper.place_id(),
            'main_category': post_helper.main_category(),
        }

        if save:
            self.post = new_maked_event['post']
            self.place_id = new_maked_event['place_id']
            self.main_category = new_maked_event['main_category']
            self.save()

        return new_maked_event

    def post_check(self):
        checker = PostChecker(self)
        return checker.summary()

    def post_check_html(self):
        checker = PostChecker(self)
        return format_html(checker.icons_html()) if checker.errors else ''
    post_check_html.short_description = 'Issues'


    def clean(self):
        error_message = ''
        # post size validation
        maximum_characters = 2000

        if len(self.post) > maximum_characters:
            error_message += f"Post text is too biig. It has {len(self.post)} characters " \
                             f"but it should have a maximum of {maximum_characters}"

        if error_message != '':
            raise ValidationError(_(error_message))


weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class PostingTime(models.Model):
    start_weekday = models.IntegerField(default=4)
    end_weekday = models.IntegerField(default=6)
    posting_time_hours = models.IntegerField(default=13)
    posting_time_minutes = models.IntegerField(default=20)
    posting_time = models.TimeField(null=True)

    def __str__(self):
        if (0 <= self.start_weekday < 7) & (0 <= self.end_weekday < 7):
            posting = (
                f"{weekdays[self.start_weekday]}-{weekdays[self.end_weekday]} "
                f"{self.posting_time_hours}:{self.posting_time_minutes:02}"
            )
            return posting
        return f"{self.posting_time_hours}:{self.posting_time_minutes}"


class Parameter(models.Model):  # Table events for posting
    site = models.CharField(max_length=500)
    parameter_name = models.CharField(max_length=500)
    value = models.CharField(max_length=500)
    commentary = models.CharField(max_length=500, null=True)
    full_value = models.TextField(blank=True, null=True)

    def __str__(self):
        return (self.site + self.parameter_name)


class Event(models.Model):
    event_id = models.CharField(max_length=30, default=random_event_id)
    title = models.CharField(max_length=500)
    post = models.TextField(default="", blank=True)
    full_text = models.TextField(default="", blank=True, null=True)
    image = models.CharField(max_length=500, blank=True, null=True)
    url = models.CharField(max_length=500, blank=True)
    post_url = models.CharField(max_length=500, blank=True, null=True)
    price = models.CharField(max_length=150, blank=True, null=True)
    address = models.CharField(max_length=500, blank=True, null=True)
    place = models.ForeignKey(Place, on_delete=models.SET_NULL, null=True, blank=True)
    category = models.CharField(max_length=500, null=True, blank=True)

    pub_datetime = models.DateTimeField('published date and time', default=timezone.now)
    from_date = models.DateTimeField("event from_date", default=default_event_date)
    to_date = models.DateTimeField("event to_date", default=default_event_date)

    def __str__(self):
        return self.title

