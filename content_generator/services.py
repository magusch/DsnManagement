from django.db.models import Q
from .models import FilterSet, EventSelection
from events.models import Events2Post

from datetime import datetime, timedelta


class FilterService:
    """Сервис для работы с фильтрами и отбором мероприятий"""

    @staticmethod
    def apply_filters(filter_set: FilterSet): # -> models.QuerySet:
        """Применяет фильтры и возвращает отфильтрованные мероприятия"""
        queryset = Events2Post.objects.all()
        params = filter_set.filter_params

        today = datetime.today()
        week_ahead = today + timedelta(days=7)

        if 'main_category' in params:
            queryset = queryset.filter(main_category_id__in=params['main_category'])

        if 'date_from' in params:
            queryset = queryset.filter(date__gte=params['date_from'])

        if 'date_to' in params:
            queryset = queryset.filter(date__lte=params['date_to'])

        if 'week_ahead' in params:
            queryset = queryset.filter(
                is_ready=True,
                from_date__gte=today,
                from_date__lt=week_ahead
            )
        if 'this_week' in params:
            start_week = today - timedelta(days=today.weekday())
            end_week = start_week + timedelta(days=7)

            queryset = queryset.filter(
                is_ready=True,
                from_date__gte=start_week,
                from_date__lt=end_week
            )

        if 'weekend' in params:
            saturday = today + timedelta(days=7 - today.weekday())
            sunday = saturday + timedelta(days=1)

            queryset = queryset.filter(
                is_ready=True,
                from_date__lte=sunday,
                to_date__gte=saturday,
            )

        if 'location' in params:
            queryset = queryset.filter(location__icontains=params['location'])

        if 'keywords' in params:
            q_objects = Q()
            for keyword in params['keywords']:
                q_objects |= Q(title__icontains=keyword) | Q(description__icontains=keyword)
            queryset = queryset.filter(q_objects)

        return queryset.distinct()


class ContentGeneratorService:
    """Сервис для генерации контента на основе подборки мероприятий"""

    @staticmethod
    def generate_post(event_selection: EventSelection, template) -> str:
        """Генерирует пост на основе подборки мероприятий и шаблона"""
        events = event_selection.selected_events.all()

        context = {
            'event_count': events.count(),
            'events_list': '\n'.join([f"• {event.title}" for event in events[:10]]),
            'date_range': ContentGeneratorService._get_date_range(events),
            'categories': ContentGeneratorService._get_categories(events),
        }

        content = template.template_text
        for key, value in context.items():
            content = content.replace(f"{{{key}}}", str(value))

        return content

    @staticmethod
    def _get_date_range(events):
        """Получает диапазон дат мероприятий"""
        if not events:
            return ""

        dates = [event.date for event in events if event.date]
        if dates:
            min_date = min(dates)
            max_date = max(dates)
            if min_date == max_date:
                return min_date.strftime("%d.%m.%Y")
            return f"{min_date.strftime('%d.%m.%Y')} - {max_date.strftime('%d.%m.%Y')}"
        return ""

    @staticmethod
    def _get_categories(events):
        """Получает список категорий мероприятий"""
        categories = set()
        for event in events:
            if hasattr(event, 'category') and event.category:
                categories.add(str(event.category))
        return ", ".join(sorted(categories))
