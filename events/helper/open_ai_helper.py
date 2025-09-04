# -*- coding: utf-8 -*-
from openai import OpenAI

from .load_parameters import ParametersManager


class OpenAIHelper:
    def __init__(self):
        self.client = OpenAI()
        self.answer = None
        param = ParametersManager()
        self.system_message = param.get_parameter('openai_system_message')
        self.user_message = param.get_parameter('openai_user_message')
        self.openai_model = param.get_parameter('openai_model') or 'gpt-4o'

    def refactor_post(self, event):
        if self.system_message is not None:
            system_message = self.system_message
        else:
            system_message = "Ты редактор-копирайтер для телеграм канала о мероприятиях в Санкт-Петербурге. У нас есть сырая информация по мероприятию необходимо адаптировать её для поста."

        if self.user_message is not None:
            user_message = self.user_message
        else:
            user_message = """Необходимо прочитать текст, заголовок и другую информацию и отредактировать их по следующим инструкциям:
                 Заголовок не должен содержать какие-то даты и упоминания места проведения мероприятия. Необходимо из текста понять какой тип мероприятия (лекция, кинопоказ, концерт, фестиваль и другие) (на кирилице), название мероприятия на кирилице нужно поставить в кавычки, если название мероприятия на латинице то кавычки не нужны. Добавить какое-нибудь яркое и необычное эмодзи в начале по смыслу или просто любое. В конечном итоге составить заголовк по шаблону "<ЭМОДЗИ> <Тип мероприятия> <Название мероприятия>". Пример (🚀 Лекция «Покорение космоса в СССР»).
                 Текст мероприятия адаптировать для того чтобы быстро понять суть мероприятия и завлечь читателей. Не делать текст слишком официальным и строгим. Также текст мероприятия не должен содержать какие-то точные даты, по возможности перевести их в указания дней недель или названия праздника. Также убрать все ссылки, спец-символы и другие мешающие вещи из текста. Из всего текста выделить основную мысль и выложить её в одном абзаце (1-3 предложения). Стиль написания должен быть упрощённым и понятным, оставить капельку любопытсва если оно присутсововало в оригинальном тексте. Текст не должен быть от первого лица. Все местоимения перефразировать в третье лицо ("они что-то сделали"). В тексте также не надо использовать необязательную информацию по типу названия места проведения, график работы и стоимость входа, если нету необходимости увеличения количества символов в посте (к примеру оригинальный текст слишком короткий)."""

        completion = self.client.chat.completions.create(
            model=self.openai_model,
            messages=[
                {"role": "system",
                 "content": system_message},
                {"role": "user",
                 "content":
                 user_message +
                     f"""Обязательно выделить категорию мероприятия, можно взять из заголовка. Выделить несколько важных тегов мероприятия. Результат выдать в виде названия информации (заголовок, текст, категория, адрес, стоимость) затем элемент в виде '=>', результат и в конце поставить точку с запятой (;).
                     Если информация не найдена просто не включать её в список, не нужно угадывать с адресом или ставить пустую цену. Изначально адрес и цена уже есть в информации, ты должен предоставлять информацию только если уверен в ней!  
                 МЕРОПРИЯТИЕ:
                 Заголовок => {event['title']};
                 Текст => {event['full_text']};
                 """}
            ]
        )

        self.answer = completion.choices[0].message.content

        return self.answer

    def parse_gpt_answer(self):
        if self.answer is None:
            return {}
        data = self.answer.split('\n')
        event_data = {}
        for d in data:
            if d.strip() == '':
                continue
            divided = d.split('=>')
            event_data[divided[0].strip()] = divided[-1].strip().replace(';','')

        if 'Текст' not in event_data or len(event_data['Текст'].strip()) < 100: event_data['Текст'] = self.answer
        return event_data

    def new_event_data(self, event):
        replace_phrases = {'Текст': 'prepared_text', 'Заголовок': 'title', 'Категория': 'category',
                           'Адрес': 'address', 'Стоимость': 'price'}
        if self.answer is None:
            self.refactor_post(event)
        ai_event_data = self.parse_gpt_answer()

        ai_event = {}
        for key, new_event_data in ai_event_data.items():
            if key not in replace_phrases.keys(): continue
            ai_event[replace_phrases[key]] = new_event_data
        return ai_event

