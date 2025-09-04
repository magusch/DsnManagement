from django.urls import path

from . import views


urlpatterns = [
    path("check_event_status/", views.check_event_status, name="check_event_status"),
    path("count_events_by_day/", views.count_events_by_day, name="count_events_by_day"),
    path("move_approved_events/", views.move_approved_events, name="move_approved_events"),
    path("remove_old_events/", views.remove_old_events, name="remove_old_events"),
    path("fill_empty_post_time/", views.fill_empty_post_time, name="fill_empty_post_time"),
    path("update_all/", views.update_all, name="update_all"),
    path("parameters_for_channel/", views.get_parameters, name="parameters_for_channel"),
    #path("<int:event_id>", views.event_post_html, name="event_post_html"),
    path("markdown_to_html/", views.markdown_to_html, name="markdown_to_html"),
    path("markdown_all_events/", views.all_events, name="all_events"),
    path("transfer_posted_events_to_site/", views.transfer_posted_events_to_site, name="transfer_posted_events_to_site"),

    path("", views.event_list, name="event_list"),
    path("<int:id>", views.event_full, name="event_full"),

    path("remake_post/<int:id>", views.remake_post, name="remake_post"),
    path("remake_post/", views.remake_post, name="remake_post_empty"),
    path("make_post/<id>", views.remake_post, {'save': 1}, name="make_post"),

    path("remake_post_ai/", views.remake_post_ai, name="remake_empty_post_by_ai"),
    path("remake_post_ai/<int:id>", views.remake_post_ai, name="remake_post_by_ai"),

    path("check_posts/", views.check_posts, name="check_posts"),

    path('add-event/', views.EventAddView.as_view(), name='add_event'),
    path('channel_api/', views.proxy_request_to_channel_api, name='channel_api')
]