# -*- coding: utf-8 -*-
import json

from openai import OpenAI

from city.models import City, get_city

from .load_parameters import ParametersManager

DEFAULT_MODEL = 'gpt-5.4-mini'
DEFAULT_REASONING_EFFORT = 'low'
DEFAULT_VERBOSITY = 'medium'
DEFAULT_MAX_OUTPUT_TOKENS = 4000

DEFAULT_SYSTEM_MESSAGE = (
    "Ты редактор-копирайтер для телеграм канала о мероприятиях {city_loc}. "
    "У нас есть сырая информация по мероприятию, необходимо адаптировать её для поста."
)


def default_system_message(city_id):
    city = get_city(city_id or City.SPB)
    city_loc = city.name_loc if city and city.name_loc else "в Санкт-Петербурге"
    return DEFAULT_SYSTEM_MESSAGE.format(city_loc=city_loc)

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
        "editorial": {"type": "object", "additionalProperties": False,
                      "properties": {"score": {"type": ["integer", "null"], "minimum": 0, "maximum": 100},
                                     "reason": {"type": "string"}},
                      "required": ["score", "reason"]},
    },
    "required": ["title", "text", "category", "tags", "address", "price", "editorial"],
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
    def __init__(self, city=City.SPB):
        self.client = OpenAI()
        self.answer = None
        self.city = city or City.SPB
        param = ParametersManager()
        self.system_message = param.get_parameter('openai_system_message', self.city)
        self.user_message = param.get_parameter('openai_user_message', self.city)
        self.openai_model = param.get_parameter('openai_model', self.city) or DEFAULT_MODEL
        self.reasoning_effort = param.get_parameter('openai_reasoning_effort', self.city) or DEFAULT_REASONING_EFFORT
        self.verbosity = param.get_parameter('openai_verbosity', self.city) or DEFAULT_VERBOSITY

    def refactor_post(self, event):
        system_message = self.system_message or default_system_message(self.city)
        user_message = self.user_message or DEFAULT_USER_MESSAGE

        event_block = f"""
МЕРОПРИЯТИЕ:
Заголовок => {event.get('title', '')};
Текст => {event.get('full_text', '')};
"""

        self.answer = self._request(
            system_message,
            user_message + OUTPUT_INSTRUCTIONS + EDITORIAL_INSTRUCTIONS + event_block,
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
        return merge_editorial_result(event, ai_event, ai_event_data.get("editorial"))


EDITORIAL_INSTRUCTIONS = """
Также верни editorial: {"score": 0–100 или null, "reason": "краткое обоснование"}.
Оцени интересность отдельного поста для местных жителей 17–29 по исходным фактам:
соответствие аудитории, конкретная причина пойти, программа/участники/формат,
отличие от типового предложения своей категории. Не награждай просто за концерт
и не штрафуй просто за лекцию. Не учитывай повторно цену, источник и историю площадки.
Не выдумывай известность артистов. 50 — обычное предложение, 75 — убедительный интерес,
90 — выдающийся кандидат с конкретными основаниями; недостаточно данных — null.
"""

def parse_breakdown(raw):
    """Parse a stored score_breakdown value into a dict.

    Historical rows are sometimes double-encoded (a JSON string containing
    JSON) depending on the code path that wrote them — unwrap both shapes.
    """
    if raw is None:
        return None
    value = raw
    for _ in range(2):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return None
    return value if isinstance(value, dict) else None


def rating_value(value):
    """Accept only finite numeric ratings on the 0..100 scale."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if 0 <= value <= 100 else None


def rating_bonus(value):
    value = rating_value(value)
    if value is None:
        return 0
    return -5 if value < 40 else -2 if value < 60 else 0 if value < 75 else 3 if value < 90 else 5


def editorial_adjustment(breakdown):
    """Small independent AI and user adjustments; never accumulate."""
    editorial = breakdown.get('editorial') or {}
    manual = breakdown.get('manual') or {}
    ai = rating_bonus(editorial.get('score')) if isinstance(editorial, dict) else 0
    user = 0
    if isinstance(manual, dict):
        if rating_value(manual.get('score')) is not None:
            user = rating_bonus(manual['score'])
        elif manual.get('target') in ('ReadyToPost', 'OnlyApi'):
            user = 5 if manual['target'] == 'ReadyToPost' else -5
    return ai + user


def routing_locked(raw):
    """Presence of a manual transfer marker excludes automatic routing."""
    bd = parse_breakdown(raw) or {}
    manual = bd.get('manual')
    return 'manual_transfer' in bd or (isinstance(manual, dict) and 'target' in manual)


def merge_editorial_result(event, answer, editorial=None):
    """Keep trusted metadata; a model may supply only its own rating."""
    result = dict(answer)
    bd = dict(parse_breakdown(event.get('score_breakdown')) or {})
    old_adjustment = editorial_adjustment(bd)
    result.pop('editorial', None)
    result.pop('score_breakdown', None)
    result.pop('score', None)
    if isinstance(editorial, dict):
        value = rating_value(editorial.get('score'))
        if value is not None:
            bd['editorial'] = {'score': value, 'reason': str(editorial.get('reason') or '')[:600], 'version': 1}
    if bd:
        if rating_value(bd.get('total')) is not None:
            base = bd.get('base_total', bd['total'] - bd.get('rating_adjustment', old_adjustment))
            bd['base_total'] = base
            bd['total'] = max(0, min(100, base + editorial_adjustment(bd)))
            bd['rating_adjustment'] = editorial_adjustment(bd)
            result['score'] = bd['total']
        result['score_breakdown'] = bd
    return result



def apply_manual_transfer(event, target):
    bd = dict(parse_breakdown(event.score_breakdown) or {})
    old_adjustment = bd.get('rating_adjustment', 0)
    manual = dict(bd.get('manual') or {})
    manual['target'] = target
    bd['manual'] = manual
    bd['manual_transfer'] = {'target': target}
    if event.score is not None:
        bd['base_total'] = bd.get('base_total', event.score - old_adjustment)
        event.score = max(0, min(100, bd['base_total'] + editorial_adjustment(bd)))
        bd['total'] = event.score
    bd['rating_adjustment'] = editorial_adjustment(bd)
    event.score_breakdown = bd
    event.status = target
    event.post_date = None
