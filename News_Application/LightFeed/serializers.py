from rest_framework import serializers
from LightFeed.models import User, Publisher, Article, Newsletter


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "role"]


class PublisherSerializer(serializers.ModelSerializer):
    editor_usernames = serializers.SerializerMethodField()

    class Meta:
        model = Publisher
        fields = ["id", "name", "description", "editors", "editor_usernames"]
        read_only_fields = ["editors"]

    def get_editor_usernames(self, obj):
        return [editor.username for editor in obj.editors.all()]


class NewsletterSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = Newsletter
        fields = ["id", "title", "description", "articles", "author",
                  "author_username", "publisher", "status"]
        read_only_fields = ["author"]


class ArticleSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    publisher_name = serializers.CharField(source="publisher.name", read_only=True)

    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "slug",
            "content",
            "author",
            "author_username",
            "publisher",
            "publisher_name",
            "approved",
            "created_at",
        ]
        # approved defaults to False via model, author injected by view
        read_only_fields = ["author", "approved", "slug", "created_at"]
