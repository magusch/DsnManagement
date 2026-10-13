from django.contrib import admin

from .models import City


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'timezone', 'is_active', 'channel_link', 'sort_order']
    list_editable = ['is_active', 'sort_order']
