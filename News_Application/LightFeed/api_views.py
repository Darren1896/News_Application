from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from LightFeed.models import Article
from .serializers import ArticleSerializer
from .permissions import IsJournalistForPost, IsAuthorOrEditorForWrite

from django.db import models


class ArticleViewSet(viewsets.ModelViewSet):
    """
    Handles standard CRUD actions:
    GET /api/articles/ -> list all approved
    GET /api/articles/<id>/ -> retrieve single
    POST /api/articles/ -> create draft (journalists only)
    PUT /api/articles/<id>/ -> update details
    DELETE /api/articles/<id>/ -> drop record
    """

    serializer_class = ArticleSerializer
    # Combine our custom structural guards
    permission_classes = [
        IsAuthenticated,
        IsJournalistForPost,
        IsAuthorOrEditorForWrite,
    ]

    def get_queryset(self):
        """Filters broad visibility rules based on request method and role
        hierarchy"""
        # If modifying a record, check against the entire database pool so
        # object permissions can run
        if self.action in ["retrieve", "update", "partial_update", "destroy"]:
            return Article.objects.all()

        # Editors see all articles to perform workflow review updates
        if (self.request.user.is_authenticated and
                self.request.user.role == "editor"):
            return Article.objects.all().order_by("-id")

        # Standard list view returns ONLY approved, published articles
        return Article.objects.filter(approved=True).order_by("-id")

    def perform_create(self, serializer):
        """Automatically attaches the logged-in journalist as the immutable
        author"""
        serializer.save(author=self.request.user, approved=False)

    @action(detail=False, methods=["get"], url_path="subscribed")
    def subscribed_feed(self, request):
        """Returns articles matching publishers or journalists the active
        reader follows"""
        user = request.user

        # Pull active subscriptions arrays from User model relationship
        # mappings
        followed_publishers = user.subscribed_publishers.all()
        followed_journalists = user.subscribed_journalists.all()

        # Query items matching either filter condition that are
        # officially published
        articles = (
            Article.objects.filter(
                models.Q(publisher__in=followed_publishers)
                | models.Q(author__in=followed_journalists),
                approved=True,
            )
            .distinct()
            .order_by("-id")
        )

        serializer = self.get_serializer(articles, many=True)
        return Response(serializer.data)
