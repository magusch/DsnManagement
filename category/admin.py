from django.contrib import admin
from .models import Category, SubCategory, EmojiMapping

admin.site.register(Category)
admin.site.register(SubCategory)


@admin.register(EmojiMapping)
class EmojiMappingAdmin(admin.ModelAdmin):
    list_display = ['emoji', 'custom_emoji_id']
    list_editable = ['custom_emoji_id']
    search_fields = ['emoji']