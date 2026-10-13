from django.contrib import admin, messages

from .models import City


def _has_city(model):
    return any(f.name == 'city' for f in model._meta.get_fields())


class CityScopedAdmin:
    """Shows only the rows of the city picked in the header switcher.

    - per-city models: rows of that city; new rows get it automatically;
    - `city_shared = True` (parameters, themes): the city's rows plus the shared 'all' rows;
    - `city_lookup` for models that get their city through a relation ('place__city').

    In the 'all' mode everything is shown, with a city column and filter.
    """

    city_lookup = 'city'
    city_shared = False

    @staticmethod
    def selected_city(request):
        return getattr(request, 'city', City.SPB)

    def scope_by_city(self, request, queryset):
        city = self.selected_city(request)
        if city == City.ALL:
            return queryset
        if self.city_shared:
            return queryset.filter(**{f'{self.city_lookup}__in': [city, City.ALL]})
        return queryset.filter(**{self.city_lookup: city})

    def collection_city(self, request):
        """City for an action over the whole queue/schedule; None (with a message) in 'all' mode."""
        city = self.selected_city(request)
        if city == City.ALL:
            self.message_user(request, 'Выберите город в шапке: действие работает с очередью одного города.',
                              messages.ERROR)
            return None
        return city

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        # Object pages open regardless of the switcher, so links from other pages keep working.
        if request.resolver_match and 'object_id' in request.resolver_match.kwargs:
            return queryset
        return self.scope_by_city(request, queryset)

    def _owns_city_field(self):
        return self.city_lookup == 'city'

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        # Per-city rows take the city from the switcher; the field is only editable in 'all' mode.
        if (self._owns_city_field() and not self.city_shared
                and self.selected_city(request) != City.ALL and 'city' in fields):
            fields.remove('city')
        return fields

    def save_model(self, request, obj, form, change):
        city = self.selected_city(request)
        if (not change and self._owns_city_field() and not self.city_shared
                and city != City.ALL):
            obj.city_id = city
        super().save_model(request, obj, form, change)

    def get_list_display(self, request):
        list_display = list(super().get_list_display(request))
        if self._owns_city_field() and (self.city_shared or self.selected_city(request) == City.ALL):
            list_display.append('city_code')
        return list_display

    @admin.display(description='Город', ordering='city')
    def city_code(self, obj):
        # The code itself: str(obj.city) would cost a query per row.
        return obj.city_id

    def get_list_filter(self, request):
        list_filter = list(super().get_list_filter(request))
        if self._owns_city_field() and self.selected_city(request) == City.ALL:
            list_filter.insert(0, 'city')
        return list_filter

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        city = self.selected_city(request)
        if city != City.ALL:
            if db_field.name == 'city' and self.city_shared:
                kwargs['queryset'] = City.objects.filter(code__in=[city, City.ALL])
            elif db_field.name != 'city' and _has_city(db_field.related_model):
                # Otherwise a Kazan event can be linked to a Petersburg place.
                kwargs['queryset'] = db_field.related_model._default_manager.filter(city=city)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        city = self.selected_city(request)
        if city != City.ALL and _has_city(db_field.related_model):
            kwargs['queryset'] = db_field.related_model._default_manager.filter(city=city)
        return super().formfield_for_manytomany(db_field, request, **kwargs)
