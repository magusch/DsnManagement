from django.db.models import Q
from .models import FilterSet
from events.models import Events2Post

from datetime import datetime, timedelta, time

from django.utils import timezone as django_tz


def _tz_offset():
    """Get UTC offset of Django TIME_ZONE setting as timedelta."""
    now = django_tz.now()
    local_now = now.astimezone(django_tz.get_current_timezone())
    return local_now.utcoffset()


def _start_of_day(dt):
    """Start of day in local tz, shifted to UTC for DB comparison."""
    if isinstance(dt, datetime):
        dt = dt.date()
    return datetime.combine(dt, time.min) - _tz_offset()


def _end_of_day(dt):
    """End of day in local tz, shifted to UTC for DB comparison."""
    if isinstance(dt, datetime):
        dt = dt.date()
    return datetime.combine(dt, time.max) - _tz_offset()


class FilterService:
    """Сервис для работы с фильтрами и отбором мероприятий.

    Logic mirrors the API's apply_filters so results are identical.
    """

    @staticmethod
    def apply_filters(filter_set: FilterSet):
        """Apply filters and return filtered events queryset."""
        params = filter_set.filter_params
        queryset = Events2Post.objects.all()

        today = datetime.today()
        week_ahead = today + timedelta(days=7)

        # Default date range (using full days to avoid timezone issues)
        date_from = _start_of_day(today)
        date_to = _end_of_day(week_ahead)

        # --- Category (positive = include, negative = exclude) ---
        if 'main_category' in params:
            categories = params['main_category']
            if not isinstance(categories, list):
                categories = [categories]
            include = [c for c in categories if c > 0]
            exclude = [abs(c) for c in categories if c < 0]
            if include:
                queryset = queryset.filter(main_category_id__in=include)
            if exclude:
                queryset = queryset.exclude(main_category_id__in=exclude)

        # --- Date overrides (order matters: specific beats general) ---
        if 'date_from' in params:
            date_from = _start_of_day(datetime.fromisoformat(params['date_from'])
                                      if isinstance(params['date_from'], str)
                                      else params['date_from'])

        if 'date_to' in params:
            date_to = _end_of_day(datetime.fromisoformat(params['date_to'])
                                  if isinstance(params['date_to'], str)
                                  else params['date_to'])

        if 'week_ahead' in params:
            date_from = _start_of_day(today)
            date_to = _end_of_day(week_ahead)

        if 'this_week' in params:
            date_from = _start_of_day(today)
            end_week = today - timedelta(days=today.weekday()) + timedelta(days=7)
            date_to = _end_of_day(end_week)

        if 'weekend' in params:
            saturday = today + timedelta(5 - today.weekday())
            sunday = saturday + timedelta(days=1)
            date_from = _start_of_day(saturday)
            date_to = _end_of_day(sunday)

        # Apply date range
        queryset = queryset.filter(
            from_date__lte=date_to,
            to_date__gte=date_from,
        )

        # --- Location ---
        if 'location' in params:
            locations = params['location']
            if not isinstance(locations, list):
                locations = [locations]
            q = Q()
            for loc in locations:
                q |= Q(address__icontains=loc)
            queryset = queryset.filter(q)

        # --- Max price ---
        if 'max_price' in params:
            try:
                max_price = int(params['max_price'])
                queryset = queryset.filter(
                    Q(price_int__lte=max_price) | Q(price_int__isnull=True)
                )
            except (ValueError, TypeError):
                pass

        # --- Keywords ---
        if 'keywords' in params:
            q = Q()
            for keyword in params['keywords']:
                q |= Q(title__icontains=keyword) | Q(full_text__icontains=keyword)
            queryset = queryset.filter(q)

        return queryset.distinct()
