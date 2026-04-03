from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

import logging

from events.utils import channel_api_request
from .models import FilterSet, PostTemplate, GeneratedPost, EventSelection
from .services import FilterService

logger = logging.getLogger("content_generator")


@staff_member_required
def wizard_view(request):
    filter_sets = FilterSet.objects.filter(is_active=True).order_by("name")
    templates = PostTemplate.objects.filter(is_active=True).order_by("name")
    template_data = {str(t.id): t.template_text for t in templates}
    context = {
        "title": "Генератор контента",
        "filter_sets": filter_sets,
        "templates": templates,
        "template_data": template_data,
        "has_permission": True,
        "site_header": "Давай с нами!",
    }
    return render(request, "content_generator/wizard.html", context)


@staff_member_required
@require_POST
def apply_filters_view(request):
    """Local DB query for display — lightweight, no need for API."""
    filter_set_id = request.POST.get("filter_set_id")
    if not filter_set_id:
        return render(request, "content_generator/partials/events_table.html", {
            "events": [], "error": "Выберите набор фильтров",
        })

    try:
        filter_set = FilterSet.objects.get(id=filter_set_id)
    except FilterSet.DoesNotExist:
        return render(request, "content_generator/partials/events_table.html", {
            "events": [], "error": "Набор фильтров не найден",
        })

    events = FilterService.apply_filters(filter_set).order_by("from_date")
    return render(request, "content_generator/partials/events_table.html", {
        "events": events,
        "total_count": events.count(),
    })


def _generate_locally(event_ids, template_id, max_events):
    """Fallback: generate post locally when API is unavailable."""
    from .utils import generate_post

    try:
        max_events = int(max_events)
    except (ValueError, TypeError):
        max_events = 15

    if not template_id:
        return JsonResponse({"error": "Выберите шаблон для локальной генерации"}, status=400)

    try:
        template = PostTemplate.objects.get(id=template_id)
    except PostTemplate.DoesNotExist:
        return JsonResponse({"error": "Шаблон не найден"}, status=400)

    from events.models import Events2Post
    events = Events2Post.objects.filter(id__in=event_ids)[:max_events]
    content = generate_post(events, template.template_text)

    return JsonResponse({
        "status": "success",
        "content": content,
        "total_count": len(event_ids),
        "fallback": True,
    })


def _send_to_api(api_url, payload):
    """Send request to channel API, return parsed JSON or error JsonResponse."""
    data = {
        "api_url": api_url,
        "method": "POST",
        "data": payload,
    }

    print(f"[API →] {api_url}  payload={payload}")

    response, error = channel_api_request(data)
    if error:
        print(f"[API ✗] {api_url}  error={error}")
        return None, error

    try:
        result = response.json()
    except Exception:
        print(f"[API ✗] {api_url}  non-json body={response.text[:500]}")
        return None, "Невалидный ответ от API"

    print(f"[API ←] {api_url}  result_keys={list(result.keys()) if isinstance(result, dict) else type(result)}")
    if isinstance(result, dict) and 'content' in result:
        print(f"[API ←] content length={len(result['content'])}")
    if isinstance(result, dict) and 'result' in result and isinstance(result['result'], dict):
        r = result['result']
        print(f"[API ←] result.keys={list(r.keys())}")
        if 'content' in r:
            print(f"[API ←] result.content length={len(r['content'])}")
    return result, None


def _api_result_to_response(result, event_ids):
    """Convert API result to JsonResponse — handles task_id and direct result."""
    if "task_id" in result:
        return JsonResponse({
            "status": "pending",
            "task_id": result["task_id"],
        })

    content = result.get("content", result.get("post", str(result)))
    resp = {
        "status": "success",
        "content": content,
        "total_count": len(event_ids),
    }
    if result.get("image"):
        resp["image"] = result["image"]
    if result.get("title"):
        resp["title"] = result["title"]
    return JsonResponse(resp)


@staff_member_required
@require_POST
def generate_post_api_view(request):
    """Send selected event IDs to channel API for post generation.

    method=code → POST /api/content-generator/generate-post/
    method=ai   → POST /api/content-generator/generate-post-ai/
    """
    event_ids = request.POST.getlist("event_ids")
    method = request.POST.get("method", "code")
    template_id = request.POST.get("template_id", "")
    max_events = request.POST.get("max_events", "15")
    title = request.POST.get("title", "")
    is_fallback = request.POST.get("fallback") == "1"

    if not event_ids:
        return JsonResponse({"error": "Не выбрано ни одного мероприятия"}, status=400)

    int_event_ids = [int(eid) for eid in event_ids]

    # Create EventSelection so API can reference it by ID
    from events.models import Events2Post
    selection = EventSelection.objects.create(
        name=title or "Wizard selection",
        filter_set=FilterSet.objects.first(),
        status="ready",
        created_by=request.user,
    )
    events = Events2Post.objects.filter(id__in=int_event_ids)
    selection.selected_events.set(events)

    if method == "ai":
        payload = {
            "event_selection_id": selection.id,
            "event_ids": int_event_ids,
        }
        if title:
            payload["title"] = title
        api_url = "api/content-generator/generate-post-ai/"
    else:
        payload = {
            "event_selection_id": selection.id,
            "event_ids": int_event_ids,
        }
        if template_id:
            payload["post_template_id"] = int(template_id)
        try:
            payload["max_events"] = int(max_events)
        except (ValueError, TypeError):
            payload["max_events"] = 15
        api_url = "api/content-generator/generate-post/"

    result, error = _send_to_api(api_url, payload)
    if error:
        if method == "code" or is_fallback:
            return _generate_locally(event_ids, template_id, max_events)
        return JsonResponse({"error": f"Ошибка API: {error}"}, status=502)

    return _api_result_to_response(result, event_ids)


@staff_member_required
@require_POST
def check_task_view(request):
    """Poll channel API for async task status."""
    task_id = request.POST.get("task_id", "")
    if not task_id:
        return JsonResponse({"error": "No task_id"}, status=400)

    data = {
        "api_url": f"api/status/{task_id}",
        "method": "GET",
        "data": {"task_id": task_id},
    }

    response, error = channel_api_request(data)
    if error:
        print(f"[POLL ✗] task={task_id}  error={error}")
        return JsonResponse({"error": error}, status=502)

    try:
        result = response.json()
    except Exception:
        return JsonResponse({"error": "Невалидный ответ"}, status=502)

    print(f"[POLL ←] task={task_id}  keys={list(result.keys()) if isinstance(result, dict) else type(result)}")
    if isinstance(result, dict) and 'result' in result and isinstance(result['result'], dict):
        r = result['result']
        print(f"[POLL ←] result.keys={list(r.keys())}")
        if 'content' in r:
            print(f"[POLL ←] result.content length={len(r['content'])}")
            print(f"[POLL ←] content first 200={r['content'][:200]}")
            print(f"[POLL ←] content last 200={r['content'][-200:]}")
    return JsonResponse(result)


@staff_member_required
@require_POST
def save_post_view(request):
    content = request.POST.get("content", "")
    event_ids = request.POST.get("event_ids", "")
    title = request.POST.get("title", "")

    if not content:
        return JsonResponse({"error": "Нет контента для сохранения"}, status=400)

    if not title:
        from django.utils import timezone
        title = f"Подборка от {timezone.now().strftime('%d.%m.%Y %H:%M')}"

    event_id_list = [eid for eid in event_ids.split(",") if eid]

    selection = None
    if event_id_list:
        from events.models import Events2Post
        selection = EventSelection.objects.create(
            name=title,
            filter_set=FilterSet.objects.first(),
            status="completed",
            created_by=request.user,
        )
        events = Events2Post.objects.filter(id__in=event_id_list)
        selection.selected_events.set(events)

    import json
    try:
        media_files = json.loads(request.POST.get("media_files", "[]"))
    except (json.JSONDecodeError, TypeError):
        media_files = []

    image = request.POST.get("image", "") or None

    post = GeneratedPost.objects.create(
        event_selection=selection,
        title=title,
        content=content,
        image=image,
        media_files=media_files,
        status="draft",
        generated_by=request.user,
    )

    from django.urls import reverse
    admin_url = reverse("admin:content_generator_generatedpost_change", args=[post.id])

    return render(request, "content_generator/partials/save_result.html", {
        "post": post,
        "admin_url": admin_url,
    })
