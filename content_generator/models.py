from django.db import models
from django.contrib.auth.models import User
from events.models import Events2Post

from django.utils import timezone


class FilterSet(models.Model):
    """Set filteres of events"""
    FILTER_TYPES = [
        ('standard', 'Стандартный'),
        ('custom', 'Пользовательский'),
    ]

    name = models.CharField(max_length=200, verbose_name='Название набора фильтров')
    description = models.TextField(blank=True, verbose_name='Описание', null=True)
    filter_type = models.CharField(max_length=20, choices=FILTER_TYPES, default='custom')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, null=True, default=1)
    created_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    filter_params = models.JSONField(default=dict, help_text='Параметры фильтрации в JSON формате')

    class Meta:
        verbose_name = 'Набор фильтров'
        verbose_name_plural = 'Наборы фильтров'

    def __str__(self):
        return self.name


class EventSelection(models.Model):
    """Выбранный набор мероприятий на основе фильтров"""
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('ready', 'Готов к обработке'),
        ('processing', 'В обработке'),
        ('completed', 'Обработан'),
    ]

    name = models.CharField(max_length=200, verbose_name='Название подборки')
    filter_set = models.ForeignKey(FilterSet, on_delete=models.CASCADE, verbose_name='Набор фильтров')
    selected_events = models.ManyToManyField(Events2Post, verbose_name='Выбранные мероприятия', blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, default=1, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    generation_settings = models.JSONField(default=dict, blank=True, null=True)

    class Meta:
        verbose_name = 'Подборка мероприятий'
        verbose_name_plural = 'Подборки мероприятий'

    def __str__(self):
        return f"{self.name} ({self.selected_events.count()} событий)"


class PostTemplate(models.Model):
    """Шаблоны для генерации постов"""
    name = models.CharField(max_length=200, verbose_name='Название шаблона')
    template_text = models.TextField(verbose_name='Текст шаблона')
    variables = models.JSONField(default=list, help_text='Список переменных в шаблоне')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Шаблон поста'
        verbose_name_plural = 'Шаблоны постов'

    def __str__(self):
        return self.name


class GeneratedPost(models.Model):
    """Сгенерированный пост на основе подборки мероприятий"""
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('scheduled', 'Запланирован'),
        ('published', 'Опубликован'),
        ('cancelled', 'Отменен'),
    ]

    event_selection = models.ForeignKey(EventSelection, on_delete=models.CASCADE, blank=True, null=True, verbose_name='Подборка мероприятий')
    post_template = models.ForeignKey(PostTemplate, on_delete=models.CASCADE, blank=True, null=True, verbose_name='Шаблон поста')

    title = models.CharField(max_length=300, verbose_name='Заголовок поста')
    content = models.TextField(verbose_name='Содержание поста')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    tags = models.JSONField(default=list, blank=True, null=True)
    media_files = models.JSONField(default=list, blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    generated_by = models.ForeignKey(User, on_delete=models.CASCADE, editable=False, default=1, null=True)

    class Meta:
        verbose_name = 'Сгенерированный пост'
        verbose_name_plural = 'Сгенерированные посты'

    def __str__(self):
        return self.title


class PostingSchedule(models.Model):
    """Расписание для постинга"""
    generated_post = models.OneToOneField(GeneratedPost, on_delete=models.CASCADE, verbose_name='Пост')
    scheduled_time = models.DateTimeField(verbose_name='Время публикации')
    platform = models.CharField(max_length=50, verbose_name='Платформа', help_text='Telegram, VK, etc.')

    platform_settings = models.JSONField(default=dict, blank=True, null=True,)

    is_posted = models.BooleanField(default=False, verbose_name='Опубликован')
    posted_at = models.DateTimeField(null=True, blank=True, verbose_name='Время публикации')

    error_message = models.TextField(blank=True, null=True, verbose_name='Сообщение об ошибке')
    retry_count = models.IntegerField(default=0, verbose_name='Количество попыток')

    created_at = models.DateTimeField(default = timezone.now)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        verbose_name = 'Расписание постинга'
        verbose_name_plural = 'Расписание постинга'
        ordering = ['scheduled_time']

    def __str__(self):
        return f"{self.generated_post.title} -> {self.platform} ({self.scheduled_time})"

