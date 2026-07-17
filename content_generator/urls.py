from django.urls import path
from . import views

urlpatterns = [
    path("wizard/", views.wizard_view, name="content_generator_wizard"),
    path("apply-filters/", views.apply_filters_view, name="cg_apply_filters"),
    path("generate-post/", views.generate_post_api_view, name="cg_generate_post"),
    path("check-task/", views.check_task_view, name="cg_check_task"),
    path("save-post/", views.save_post_view, name="cg_save_post"),
]
