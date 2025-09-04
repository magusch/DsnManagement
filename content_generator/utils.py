from events.utils import channel_api_request


def generate_post(events, template):
    """
    events: QuerySet или список объектов Events2Post
    template: строка-шаблон с переменными
    """
    blocks = []
    for event in events:
        block = template.format(
            title=event.title or "",
            price=event.price or "Бесплатно",
            prepared_text=event.prepared_text or "",
            address=event.address or "",
        )
        blocks.append(block.strip())
    return "\n\n---\n\n".join(blocks)


def event_selection_by_filter_id(filter_id):
    data = {
        "api_url": "api/content_generator_event_selection/",
        "method": "POST",
        "data": {"filter_set_id": filter_id[0]}
    }

    response = channel_api_request(data)
    if response.status_code == 200:
        return True


def generate_post_api(event_selection_id, template_id):
    data = {
        "api_url": "api/content_generator_generate_post/",
        "method": "POST",
        "data": {
            "event_selection_id": event_selection_id,
            "post_template_id": template_id,
            #"user_id": user_id
        }
    }

    response = channel_api_request(data)
    if response.status_code == 200:
        return True
