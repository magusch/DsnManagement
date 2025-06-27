import re, os

from place.utils import address_from_places, place_orm_object

from .datetime_helper import weekday_name, month_name

from category.models import SubCategory

import pytz

from datetime import datetime

TELEGRAM_BOT_NAME = os.environ.get("TELEGRAM_BOT_NAME", None)

class PostHelper:
    def __init__(self, event):
        self.TIMEZONE = pytz.timezone("Europe/Moscow")
        if type(event) == dict:
            event = DictAsMethods(event)
        self.event = event
        self.dates_to_right_tz()

        from .load_parameters import ParametersManager
        self.param_manager = ParametersManager()

    def dates_to_right_tz(self):
        if type(self.event.from_date) == str:
            self.event.from_date = datetime.fromisoformat(self.event.from_date)
        if type(self.event.to_date) == str:
            self.event.to_date = datetime.fromisoformat(self.event.to_date)

        self.event.from_date = self.event.from_date.astimezone(self.TIMEZONE)
        self.event.to_date = self.event.to_date.astimezone(self.TIMEZONE)

    def get_event_name(self):
        return f"Event: {self.title}"

    def _title_markdown(self):
        title = self.event.title
        title = title.replace("`", r"\`").replace("_", r"\_").replace("*", r"\*")

        # title = re.sub(r"[\"'‘](?=[^\ \.!\n])", "«", title)
        # title = re.sub(r"[\"'‘](?=[^a-zA-Zа-яА-Я0-9]|$)", "»", title)
        title = re.sub(r'["\'](\S.*?)["\']', r'«\1»', title)

        if '«' in title and '»' in title:
            pattern = r'(«[^»]*»)'
            title = re.sub(pattern, r'*\1*', title)
        elif re.search(r'[A-Za-z]', title):
            pattern = r'(\b[A-Za-z0-9]+\b(?: \b[A-Za-z0-9]+\b)*)'
            title = re.sub(pattern, r'*\1*', title)
        elif re.search(r'[A-ZА-Я]{3,}', title):
            pattern = r'(\b[A-ZА-Я]{3,}\b(?: \b[A-ZА-Я0-9]{1,}\b)*)'
            title = re.sub(pattern, r'*\1*', title)
        else:
            title = f"{title[0]}*{title[1:]}*"

        return title

    def post_markdown(self) -> object:
        title = self._title_markdown()

        date_from_to = self.date_to_post()

        title_date = self.date_to_title()

        full_title = f"*{title_date}* {title}\n\n"

        if not self.event.prepared_text and not self.event.full_text :
            post_text = self.event.post
        elif not self.event.prepared_text:
            post_text = self.reduce_text(self.event.full_text)
        else:
            post_text = self.reduce_text(self.event.prepared_text)

        post_text = (
            post_text.strip()
                .replace("`", r"\`")
                .replace("_", r"\_")
                .replace("*", r"\*")
        )

        address_line = self.address_markdown()

        footer_link = self.param_manager.get_parameter('finish_link')
        if not footer_link: footer_link = ''

        remind_link = ''
        if TELEGRAM_BOT_NAME is not None:
            remind_link = f"|| [Сохранить в боте](https://t.me/{TELEGRAM_BOT_NAME}?start=save-{self.event.id})"


        footer = (
            "\n\n"
            f"*Где:* {address_line}\n"
            f"*Когда:* {date_from_to} \n"
            f"*Вход:* [{self.event.price}]({self.event.url})"
            f"\n\n{footer_link} {remind_link}"
        )

        full_post = (full_title + post_text.strip() + footer).strip()
        return full_post

    def address_markdown(self):
        address_line = None

        need_address_line_url = self.param_manager.get_parameter('need_address_line_url')
        if need_address_line_url:
            if need_address_line_url.lower() in ('true', '1'):
                need_address_line_url = True
            else:
                need_address_line_url = False

        if hasattr(self.event, 'place_id'):
            if self.event.place_id:
                place = place_orm_object(self.event.place_id)
                address_line = place.markdown_address(need_address_line_url)

        if address_line is None:
            raw_address = self.event.address
            addresses = address_from_places(raw_address)

            if addresses:
                address_line = addresses[0].place.markdown_address(need_address_line_url)
                if hasattr(self.event, 'place_id'):
                    self.event.place_id = addresses[0].place.id
            else:
                if need_address_line_url:
                    address_line = \
                        f"[{self.event.address}](https://2gis.ru/spb/search/{self.event.address})"
                else:
                    address_line = self.event.address

        return address_line

    def place_id(self):
        raw_address = self.event.address
        addresses = address_from_places(raw_address)
        if hasattr(self.event, 'place_id'):
            if self.event.place_id is None and addresses:
                self.event.place_id = addresses[0].place.id
        elif addresses:
            self.event.place_id = addresses[0].place.id
        else:
            self.event.place_id = None

        return self.event.place_id

    def date_to_title(self):
        date_from = self.event.from_date
        date_to = self.event.to_date

        if date_to is None:
            title_date = "{day} {month}".format(
                day=date_from.day,
                month=month_name(date_from),
            )
        elif date_from.month != date_to.month:
            title_date = "{day_s} {month_s} – {day_e} {month_e}".format(
                day_s=date_from.day,
                month_s=month_name(date_from),
                day_e=date_to.day,
                month_e=month_name(date_to)
            )
        elif date_to.day - date_from.day == 1:
            title_date = "{day_s} и {day_e} {month_s}".format(
                day_s=date_from.day,
                month_s=month_name(date_from),
                day_e=date_to.day
            )
        elif date_from.day != date_to.day:
            title_date = "{day_s} – {day_e} {month_s}".format(
                day_s=date_from.day,
                month_s=month_name(date_from),
                day_e=date_to.day
            )
        else:
            title_date = "{day} {month}".format(
                day=date_from.day,
                month=month_name(date_from),
            )
        return title_date

    def date_to_post(self):
        date_from = self.event.from_date
        date_to = self.event.to_date

        s_weekday = weekday_name(date_from)
        s_day = date_from.day
        s_month = month_name(date_from)
        s_hour = date_from.hour
        s_minute = date_from.minute

        if date_to is not None:
            e_weekday = weekday_name(date_to)
            e_day = date_to.day
            e_month = month_name(date_to)
            e_hour = date_to.hour
            e_minute = date_to.minute

            if s_day == e_day:
                start_format = f"{s_weekday}, {s_day} {s_month} {s_hour:02}:{s_minute:02}-"
                end_format = f"{e_hour:02}:{e_minute:02}"

            elif s_month != e_month:
                start_format = f"{s_weekday}-{e_weekday}, {s_day} {s_month} - "
                end_format = f"{e_day} {e_month} {s_hour:02}:{s_minute:02}–{e_hour:02}:{e_minute:02}"
            else:
                start_format = f"{s_weekday}-{e_weekday}, {s_day}–{e_day} {s_month} {s_hour:02}:{s_minute:02}-"
                end_format = f"{e_hour:02}:{e_minute:02}"

        else:
            end_format = ""
            start_format = f"{s_weekday}, {s_day} {s_month} {s_hour:02}:{s_minute:02}"

        return start_format + end_format

    def main_category(self):
        if hasattr(self.event, 'category') and self.event.category is not None:
            subcategory, created = SubCategory.objects.get_or_create(name=self.event.category)
            return subcategory.category

    def reduce_text(self, post_text):
        if len(post_text) > 550:
            sentences = post_text.split(".")
            post = ""
            for s in sentences:
                if len(post) < 365:
                    post = post + s + "."
                else:
                    post_text = post
                    break
        return post_text


class DictAsMethods(object):
    def __init__(self, data):
        self.data = data

    def __getattr__(self, name):
        if name in self.data:
            return self.data[name]
        else:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name == 'data':
            super().__setattr__(name, value)
        else:
            self.data[name] = value
