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

    try:
        int_ids = [int(eid) for eid in event_ids]
    except (ValueError, TypeError) as e:
        logger.error("[LOCAL] Bad event_ids: %s — %s", event_ids, e)
        return JsonResponse({"error": f"Некорректные ID событий: {event_ids}"}, status=400)

    if not template_id:
        return JsonResponse({"error": "Выберите шаблон для локальной генерации"}, status=400)

    try:
        template = PostTemplate.objects.get(id=template_id)
    except PostTemplate.DoesNotExist:
        logger.error("[LOCAL] Template id=%s not found", template_id)
        return JsonResponse({"error": "Шаблон не найден"}, status=400)

    from events.models import Events2Post
    events = list(Events2Post.objects.select_related('place').filter(id__in=int_ids)[:max_events])
    content = generate_post(events, template.template_text)

    logger.info("[LOCAL] %d events, content length=%d", len(events), len(content))

    if not content:
        logger.warning("[LOCAL] Empty content for ids=%s", int_ids)
        return JsonResponse({"error": "Не удалось сгенерировать пост — события не найдены"}, status=400)

    return JsonResponse({
        "status": "success",
        "content": content,
        "total_count": len(int_ids),
        "fallback": True,
    })


def _send_to_api(api_url, payload):
    """Send request to channel API, return parsed JSON or error JsonResponse."""
    data = {
        "api_url": api_url,
        "method": "POST",
        "data": payload,
    }

    response, error = channel_api_request(data)
    if error:
        logger.warning("[API] %s error: %s", api_url, error)
        return None, error

    try:
        result = response.json()
    except Exception:
        logger.error("[API] %s non-json response: %s", api_url, response.text[:300])
        return None, "Невалидный ответ от API"

    logger.info("[API] %s → %s", api_url,
                list(result.keys()) if isinstance(result, dict) else type(result))
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

    logger.info("[GENERATE] method=%s events=%d fallback=%s", method, len(event_ids), is_fallback)

    if not event_ids:
        return JsonResponse({"error": "Не выбрано ни одного мероприятия"}, status=400)

    int_event_ids = [int(eid) for eid in event_ids]

    # Fallback — skip API entirely, generate locally
    if is_fallback:
        logger.info("[GENERATE] Fallback to local generation")
        return _generate_locally(int_event_ids, template_id, max_events)

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
        logger.info("[GENERATE] API failed, falling back locally")
        if method == "code":
            return _generate_locally(int_event_ids, template_id, max_events)
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
        logger.warning("[POLL] task=%s error: %s", task_id, error)
        return JsonResponse({"error": error}, status=502)

    try:
        result = response.json()
    except Exception:
        return JsonResponse({"error": "Невалидный ответ"}, status=502)

    status = result.get("status", "?") if isinstance(result, dict) else "?"
    if status not in ("pending", "processing"):
        logger.info("[POLL] task=%s status=%s", task_id, status)
    return JsonResponse(result)


@staff_member_required
@require_POST
def save_post_view(request):
    content = request.POST.get("content", "")
    event_ids = request.POST.get("event_ids", "")
    title = request.POST.get("title", "")

    logger.info("[SAVE] title=%s content_len=%d event_ids=%s",
                title[:50], len(content), event_ids[:100])

    if not content:
        return render(request, "content_generator/partials/save_result.html", {
            "error": "Нет контента для сохранения",
        })

    if not title:
        from django.utils import timezone
        title = f"Подборка от {timezone.now().strftime('%d.%m.%Y %H:%M')}"

    try:
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
            logger.info("[SAVE] Selection id=%s, events=%d", selection.id, events.count())

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
        logger.info("[SAVE] Post created id=%s", post.id)

        from django.urls import reverse
        admin_url = reverse("admin:content_generator_generatedpost_change", args=[post.id])

        return render(request, "content_generator/partials/save_result.html", {
            "post": post,
            "admin_url": admin_url,
        })

    except Exception as e:
        logger.exception("[SAVE] Error saving post: %s", e)
        return render(request, "content_generator/partials/save_result.html", {
            "error": f"Ошибка сохранения: {e}",
        })
