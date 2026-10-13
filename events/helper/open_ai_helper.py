# -*- coding: utf-8 -*-
import json

from openai import OpenAI

from .load_parameters import ParametersManager

DEFAULT_MODEL = 'gpt-5.4-mini'
DEFAULT_REASONING_EFFORT = 'low'
DEFAULT_VERBOSITY = 'medium'
DEFAULT_MAX_OUTPUT_TOKENS = 4000

DEFAULT_SYSTEM_MESSAGE = (
    "Ты редактор-копирайтер для телеграм канала о мероприятиях в Санкт-Петербурге. "
    "У нас есть сырая информация по мероприятию, необходимо адаптировать её для поста."
)

DEFAULT_USER_MESSAGE = """Необходимо прочитать текст, заголовок и другую информацию и отредактировать их по следующим инструкциям.

ЗАГОЛОВОК
Заголовок не должен содержать какие-то даты и упоминания места проведения мероприятия. Необходимо из текста понять какой тип мероприятия (лекция, кинопоказ, концерт, фестиваль и другие) (на кириллице), название мероприятия на кириллице нужно поставить в кавычки, а если название мероприятия на латинице то кавычки не нужны. Добавить какое-нибудь яркое и необычное эмодзи в начале — по смыслу или без смысла, но не слишком банальное и часто используемое (допустим гитара для рок-концерта или книга для книжного вечера это слишком общее и банальное, но при этом если тема про лягушек, то добавить лягушку можно). В конечном итоге составить заголовок по шаблону "<ЭМОДЗИ> <Тип мероприятия> <Название мероприятия>". Пример (🚀 Лекция «Покорение космоса в СССР»).

ТЕКСТ
При создании текста мероприятия твоя задача — написать краткое, но ёмкое описание для анонса мероприятия в стиле современного городского медиа. Стиль — информативный, но не сухой; цепляющий, но не рекламный. Текст должен выглядеть как редакторская выжимка сути, а не как личный опыт.
1. Начинай с факта, а не с настроения. Первое предложение должно называть конкретную, проверяемую вещь из исходного текста — имя, произведение, формат, историческую деталь, число. Запрещены атмосферные зачины-декорации: "Погрузитесь в мир...", "Откройте дверь в...", "Добро пожаловать в...", "В этот вечер наступит...", "Приготовьтесь к путешествию..." — и любые их аналоги. Не начинай с "Есть такое шоу...". Не повторяй в тексте заголовок целиком.
2. Раскрой "фишку": чётко опиши, в чём уникальность или главная особенность события. Что там происходит и как это работает? Фокусируйся на процессе, а не на эмоциях, которые должен испытать читатель.
3. Стиль и тон: используй простой и ясный язык. Тон — нейтрально-заинтересованный. Текст должен быть по сути, без "воды", но с сохранением интриги, если она уместна. Если фактов в источнике мало — не растягивай текст образностью, лучше сократи до 2 предложений с тем, что реально есть.
4. Также делай текст по стилю времени и немного молодёжно. Иногда можно упрощать конструкцию предложения, а некоторые слова можно заменять англицизмами. К примеру для рок-концерта вместо "коллектив" лучше писать "группа", вместо "в программе фестиваля прозвучат такие коллективы" заменить упрощением "в лайнапе фестиваля:".
5. Третье лицо, без обращений к читателю. Никакого "я"/"мы" от лица организаторов. Никакого прямого обращения на "вы" ("вы окажетесь", "вас ждёт сюрприз"). Пиши о событии как наблюдатель: "артисты делают", "организаторы придумали", "зрителей ждёт" (это нормально — здесь "зрители" грамматическое подлежащее, а не обращение к читателю).
6. Очистка:
   - Даты переводи в дни недели или названия праздников (например, "в ближайшую субботу", "на выходных").
   - Убирай все ссылки, спецсимволы, цены, адреса и точное время (если это не ключевая часть формата) — вся эта информация будет в посте отдельно, и в тексте она нужна только для поддержания стиля.
7. Строгие запреты:
   - Никаких рекламных превосходных степеней и клише: "уникальный", "невероятный", "незабываемый", "потрясающий", "восхитительный" — и абстрактных слов того же рода: "магия", "волшебство", "тайна", "атмосфера", "чудо", "шарм". Если хочется использовать одно из них — замени конкретной деталью. Два и больше таких слова в одном тексте — признак, что текст надо переписать.
   - Никаких повелительных наклонений: "приготовьтесь", "приходите", "не пропустите", "посетите", "узнайте".
   - Никакого предсказания эмоций ("вы удивитесь", "будет весело").
   - Никаких восклицательных знаков.

Пример (было → стало):
Исходный текст: "Друзья! Ждем всех на невероятный концерт группы N в эту пятницу! Это будет незабываемый вечер, вы точно не пожалеете! Билеты уже в продаже, торопитесь!"
Результат: "Группа N выступит в клубе с программой из нового альбома и старых хитов. Сет разделён на два блока — акустический и электрический, с перерывом на разговор с залом."

Конечный результат по тексту: 2-4 предложения (до 1000 символов), которые идеально вписываются в структурированный анонс, помогают читателю быстро понять формат мероприятия и соответствуют всем 7 правилам выше."""

OUTPUT_INSTRUCTIONS = """
ФОРМАТ ОТВЕТА
Верни строго JSON по заданной схеме:
- title — готовый заголовок по правилам выше;
- text — готовый текст анонса по правилам выше;
- category — категория мероприятия (можно вывести из заголовка);
- tags — несколько важных тегов мероприятия;
- address — адрес, price — стоимость.
Адрес и цену возвращай только если они явно есть в исходной информации и ты в них уверен. Не угадывай и не придумывай их: если данных нет — верни null. Пустую строку вместо null не используй.
"""

EVENT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "text": {"type": "string"},
        "category": {"type": ["string", "null"]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "address": {"type": ["string", "null"]},
        "price": {"type": ["string", "null"]},
    },
    "required": ["title", "text", "category", "tags", "address", "price"],
}

FIELD_MAP = {
    'title': 'title',
    'text': 'prepared_text',
    'category': 'category',
    'address': 'address',
    'price': 'price',
    'Заголовок': 'title',
    'Текст': 'prepared_text',
    'Категория': 'category',
    'Адрес': 'address',
    'Стоимость': 'price',
}


class OpenAIHelper:
    def __init__(self):
        self.client = OpenAI()
        self.answer = None
        param = ParametersManager()
        self.system_message = param.get_parameter('openai_system_message')
        self.user_message = param.get_parameter('openai_user_message')
        self.openai_model = param.get_parameter('openai_model') or DEFAULT_MODEL
        self.reasoning_effort = param.get_parameter('openai_reasoning_effort') or DEFAULT_REASONING_EFFORT
        self.verbosity = param.get_parameter('openai_verbosity') or DEFAULT_VERBOSITY

    def refactor_post(self, event):
        system_message = self.system_message or DEFAULT_SYSTEM_MESSAGE
        user_message = self.user_message or DEFAULT_USER_MESSAGE

        event_block = f"""
МЕРОПРИЯТИЕ:
Заголовок => {event.get('title', '')};
Текст => {event.get('full_text', '')};
"""

        self.answer = self._request(
            system_message,
            user_message + OUTPUT_INSTRUCTIONS + event_block,
        )

        return self.answer

    def _request(self, system_message, user_message):
        """Send the request to the model.

        GPT-5.x models are driven through the Responses API: that is where
        reasoning.effort / text.verbosity and strict structured outputs live.
        Chat Completions is kept as a fallback for older openai SDK versions.
        """
        if hasattr(self.client, 'responses'):
            text_options = {
                "format": {
                    "type": "json_schema",
                    "name": "event_post",
                    "strict": True,
                    "schema": EVENT_JSON_SCHEMA,
                },
            }
            if self.verbosity != 'off':
                text_options["verbosity"] = self.verbosity

            response = self.client.responses.create(
                model=self.openai_model,
                instructions=system_message,
                input=user_message,
                reasoning={"effort": self.reasoning_effort},
                max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
                text=text_options,
            )
            return response.output_text

        completion = self.client.chat.completions.create(
            model=self.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
        )
        return completion.choices[0].message.content

    def parse_gpt_answer(self):
        if self.answer is None:
            return {}

        event_data = self._parse_json_answer()
        if event_data is not None:
            return event_data

        # Parsing failed — fall back to putting the raw answer into the text,
        # same as the previous behaviour.
        event_data = self._parse_legacy_answer()
        if len(event_data.get('Текст', '').strip()) < 100:
            event_data['Текст'] = self.answer
        return event_data

    def _parse_json_answer(self):
        try:
            data = json.loads(self.answer)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return {k: v for k, v in data.items() if v not in (None, '', [])}

    def _parse_legacy_answer(self):
        """Parse the legacy plain-text format `Заголовок => value;`."""
        event_data = {}
        for line in self.answer.split('\n'):
            if line.strip() == '':
                continue
            divided = line.split('=>')
            event_data[divided[0].strip()] = divided[-1].strip().replace(';', '')
        return event_data

    def new_event_data(self, event):
        if self.answer is None:
            self.refactor_post(event)
        ai_event_data = self.parse_gpt_answer()

        ai_event = {}
        for key, value in ai_event_data.items():
            if key not in FIELD_MAP:
                continue
            if isinstance(value, list):
                value = ', '.join(str(v) for v in value)
            ai_event[FIELD_MAP[key]] = value
        return ai_event
