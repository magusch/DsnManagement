# Сайт "Давай с нами!"

## Запуск
Для запуска сайта локально (для разработки), необходимо выполнить команду
```
$ python manage.py runserver
```
Сервер поднимается по адресу `http://127.0.0.1:8000/`

### Editorial rating and manual channel selection

No migration: `Events2Post.score_breakdown` is already a JSONField (PostgreSQL JSONB).
Local preparation returns the full object, including `editorial.score` (0–100),
`editorial.reason`, `score` and preserved manual/publication metadata. The admin
form serializes JSON objects before filling the textarea.

Changing status to ReadyToPost or OnlyApi in the form or bulk action adds
`manual_transfer: {"target": "ReadyToPost"}` (or OnlyApi) and `manual.target`.
ChannelBot checks marker presence and skips automatic routing, regardless of rating.
Without an optional user rating, these choices add +5/−5 once. To rate explicitly,
add `"score": 100` under `manual` in the existing JSON field; valid ratings are 0–100.
Ratings contribute −5/−2/0/+3/+5 for bands <40/<60/<75/<90/≤100. User rating alone
is not a routing lock. Base score and adjustment are stored separately to avoid
accumulation. The action “Разрешить автоматический выбор канала/API” removes the
transfer lock, preserves the rating and allows channel selection again.

Deploy with the matching ChannelBot changes. Old manual decisions have no marker;
reapply important choices before enabling `features.channel_selection.enabled`.
Historical Posted rows are not eligible for return unless digest-only publication
is explicitly recorded. No history is inferred or backfilled.
