from django.db import models

from django.apps import apps

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    name = models.CharField(max_length=250)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name_plural = "sub categories"

    def __str__(self):
        return f"{self.name} ({self.category if self.category else 'Без категории'})"

    def save(self, *args, **kwargs):
        if not self.category:
            other_category, created = Category.objects.get_or_create(name="Other")
            self.category = other_category

        Events2Post = apps.get_model('events', 'Events2Post')
        Events2Post.objects.filter(category=self.name).exclude(main_category=self.category).update(main_category=self.category)
        super().save(*args, **kwargs)