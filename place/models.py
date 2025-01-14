from django.db import models
from django.utils.translation import gettext_lazy as _


class Place(models.Model):
    place_name = models.CharField(max_length=500)
    place_address = models.CharField(max_length=2000, blank=True,)
    place_url = models.CharField(max_length=500, blank=True,)
    url_to_address = models.CharField(max_length=500, blank=True,)
    place_image = models.CharField(max_length=1000, blank=True, )
    image_upload = models.ImageField(upload_to='place_images/', blank=True, null=True)
    place_metro = models.CharField(max_length=500, blank=True,)
    place_city = models.CharField(max_length=500, default='SPb', blank=True,)

    def markdown_address(self, with_url=True):
        markdown_address = ''
        if self.url_to_address != '' and with_url is True:
            markdown_address += f"[{self.place_name}, {self.place_address}]({self.url_to_address})"
        else:
            markdown_address += f"{self.place_name}, {self.place_address}"

        if self.place_metro != '':
            markdown_address += f", м.{self.place_metro}"

        return markdown_address

    def get_schedule_str(self):
        weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вск']

        schedules = PlaceSchedule.objects.filter(place=self).order_by('weekday')

        schedule_by_weekday = {}

        for schedule in schedules:
            if schedule.weekday is not None:
                key = f"{schedule.open_time.strftime('%H:%M')}-{schedule.close_time.strftime('%H:%M')}"
                if key in schedule_by_weekday.keys():
                    schedule_by_weekday[key].append(schedule.weekday)
                else:
                    schedule_by_weekday[key] = [schedule.weekday]

        result = []
        for time_string, wkd_days in schedule_by_weekday.items():
            day_string = weekdays[wkd_days[0]]
            first_weekday = wkd_days[0]
            last_weekday = wkd_days[0]
            for i, day in enumerate(wkd_days):
                if i == 0: continue
                if last_weekday + 1 == day:
                    last_weekday = day
                elif i == len(wkd_days):
                    day_string += f"-{weekdays[wkd_days[i]]}"
                else:
                    if first_weekday != last_weekday:
                        day_string += f"-{weekdays[last_weekday]}"
                    day_string += f", {weekdays[wkd_days[i]]}"

                    first_weekday = wkd_days[i]
                    last_weekday = wkd_days[i]

            if first_weekday != last_weekday:
                day_string += f"-{weekdays[last_weekday]}"
            day_string += f" {time_string}"

            result.append(day_string)

        return "\n".join(result)

    def __str__(self):
        return f"{self.place_name}, {self.place_address}"


WEEKDAYS = [
    (None, _("-")),
    (0, _("Monday")),
    (1, _("Tuesday")),
    (2, _("Wednesday")),
    (3, _("Thursday")),
    (4, _("Friday")),
    (5, _("Saturday")),
    (6, _("Sunday"))
]

class PlaceSchedule(models.Model):
    SCHEDULE_TYPES = [
        ('std', 'Standard'),
        ('hol', 'Holiday'),
        ('spl', 'Special'),
    ]

    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name="schedules")
    schedule_type = models.CharField(max_length=10, choices=SCHEDULE_TYPES, default='std')
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    open_time = models.TimeField(null=True, blank=True, default='10:00:00')
    close_time = models.TimeField(null=True, blank=True, default='18:00:00')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["place", "schedule_type", "weekday", "date"],
                name="unique_schedule"
            ),
            models.CheckConstraint(
                check=(
                        (models.Q(schedule_type="std") & models.Q(date__isnull=True) & models.Q(
                            weekday__isnull=False)) |
                        (models.Q(schedule_type="spl") & models.Q(date__isnull=False) & models.Q(
                            weekday__isnull=True)) |
                        (models.Q(schedule_type="hol") & models.Q(
                            weekday__isnull=True))
                ),
                name="valid_schedule_type_constraint"
            )
        ]

    def __str__(self):
        if self.schedule_type == 'std':
            return f"{self.place.place_name} - {self.get_schedule_type_display()} (weekday: {self.get_weekday_display()})"
        else:
            return f"{self.place.place_name} - {self.get_schedule_type_display()} (date: {self.date})"


class PlaceKeyword(models.Model):
    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    place_keyword = models.CharField(max_length=200)

    def __str__(self):
        return (f"{self.place_keyword}, {self.place.place_address}")


class TestEventPlace(models.Model):
    event_name = models.CharField(max_length=200)
    event_address = models.CharField(max_length=200)
    place_keyword = models.ForeignKey(PlaceKeyword, on_delete=models.CASCADE)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        return models.CharField(queryset=PlaceKeyword.objects.all())
        #return super().formfield_for_foreignkey(db_field, request, **kwargs)


    def save_model(self, request, obj, form, change):
        obj.event_address = obj.event_name
        super().save_model(request, obj, form, change)

    def __str__(self):
        return (self.event_name)

    def save_formset(self, request, form, formset, change):
        print(self.event_name)
