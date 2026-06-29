from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from . import api_views, views

# Initialize Django REST Framework Router
router = DefaultRouter()
router.register(r"articles", api_views.ArticleViewSet, basename="article")

app_name = "LightFeed"

urlpatterns = [
    # =====================================================================
    # 1. AUTHENTICATION & CORE DASHBOARD
    # =====================================================================
    path("", views.login_user, name="login"),
    path("welcome/", views.welcome_page, name="welcome"),
    path("register/", views.register_user, name="register"),
    path("logout/", views.logout_user, name="logout"),

    # =====================================================================
    # 1b. DASHBOARD GROUP HUBS (Step 5: grouped navigation)
    # =====================================================================
    path("hub/news-feed/", views.news_feed_hub, name="news_feed_hub"),
    path("hub/publishers/", views.publishers_hub, name="publishers_hub"),
    path("hub/articles/", views.articles_hub, name="articles_hub"),
    path("hub/newsletters/", views.newsletters_hub, name="newsletters_hub"),

    # =====================================================================
    # 2. PUBLISHER ROUTE CONFIGURATION ENGINE
    # =====================================================================
    path("publishers/", views.view_publishers, name="view_publishers"),
    path("publishers/manage/", views.manage_publishers,
         name="manage_publishers"),
    path("publishers/create/", views.create_publisher,
         name="create_publisher"),
    path("publishers/edit/<int:pub_id>/", views.edit_publisher,
         name="edit_publisher"),
    path("publishers/delete/<int:pub_id>/", views.delete_publisher,
         name="delete_publisher"),

    # =====================================================================
    # 2b. JOURNALIST DIRECTORY
    # =====================================================================
    path("journalists/", views.view_journalists, name="view_journalists"),

    # =====================================================================
    # 2c. READER SUBSCRIPTIONS (FOLLOW PUBLISHERS / JOURNALISTS)
    # =====================================================================
    path("subscribe/<str:target_type>/<int:target_id>/",
         views.toggle_subscription, name="toggle_subscription"),

    # =====================================================================
    # 3. ARTICLE MANAGEMENT ROUTE PIPELINE
    # =====================================================================
    path("articles/", views.view_articles, name="view_articles"),
    path("articles/add/", views.add_article, name="add_article"),
    path("articles/manage/", views.manage_articles, name="manage_articles"),

    # Preloaded field parameter edit route: Expects specific dynamic index ID
    path("articles/edit/<int:article_id>/", views.edit_article_detail,
         name="edit_article_detail"),

    # Consolidated Approval endpoint: Only accessible to assigned editors
    path("articles/publish/<int:article_id>/", views.publish_draft,
         name="publish_draft"),
    path("articles/delete/<int:article_id>/", views.delete_article_page,
         name="delete_article_page"),

    # =====================================================================
    # 4. NEWSLETTERS OPERATIONAL SUITE MAPPINGS
    # =====================================================================
    path("newsletters/manage/", views.manage_newsletters,
         name="manage_newsletters"),
    path("newsletters/add/", views.add_newsletter, name="add_newsletter"),
    path("newsletters/approve/<int:newsletter_id>/", views.approve_newsletter,
         name="approve_newsletter"),
    path("newsletters/edit/<int:newsletter_id>/", views.edit_newsletter,
         name="edit_newsletter"),
    path("newsletters/delete/<int:newsletter_id>/", views.delete_newsletter,
         name="delete_newsletter"),
    path("newsletters/", views.published_newsletters,
         name="published_newsletters"),

    # =====================================================================
    # 5. PASSWORD RECOVERY MANAGEMENT SYSTEM
    # =====================================================================
    path("request-password-reset/", views.send_password_reset_email,
         name="request_password_reset"),
    path("reset_password/<str:token>/", views.reset_user_password,
         name="password_reset_form"),

    # =====================================================================
    # 6. RESTFUL API ENDPOINTS (THIRD-PARTY SECURITY TOKENS)
    # =====================================================================
    path("api/token/", obtain_auth_token, name="api_token_auth"),
    path("api/login/", obtain_auth_token, name="api_login_auth"),
    path("api/", include(router.urls)),
]
