from django.db import models
from django.utils.text import slugify
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils import timezone


class ResetToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,  # Keeps database clean on user deletion
        related_name="reset_tokens",
    )

    token = models.CharField(max_length=40, unique=True)
    expiration = models.DateTimeField()
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reset token for {self.user.username}"

    def is_expired(self):
        """Check if token has expired"""
        return timezone.now() > self.expiration

    def is_valid(self):
        """Check if token is valid (not used and not expired)"""
        return not self.used and not self.is_expired()

    class Meta:
        ordering = ["-created_at"]


class User(AbstractUser):
    """
    Custom user model extending AbstractUser to support explicit role
    definitions.
    Includes memory-safe clean checking parameters to enforce boundary
    limitations.
    """
    ROLE_CHOICES = [
        ('reader', 'Reader'),
        ('journalist', 'Journalist'),
        ('editor', 'Editor'),
    ]
    role = models.CharField(max_length=15, choices=ROLE_CHOICES,
                            default='reader')

    subscribed_publishers = models.ManyToManyField(
        'Publisher', blank=True, related_name='reader_subscribers')
    subscribed_journalists = models.ManyToManyField(
        'self', blank=True, symmetrical=False, related_name='reader_followers')

    def clean(self):
        """Enforces operational domain boundaries safely using
        memory lookups."""
        super().clean()
        if self.pk is not None:
            if self.role in ['journalist', 'editor']:
                if self.subscribed_publishers.exists() or self.subscribed_journalists.exists():
                    raise ValidationError(
                        "Content creators cannot have active Reader"
                        "subscriptions.")
            elif self.role == 'reader':
                if hasattr(self, 'published_articles'
                           ) and self.published_articles.exists():
                    raise ValidationError("Readers cannot publish Articles.")
                if hasattr(self, 'published_newsletters'
                           ) and self.published_newsletters.exists():
                    raise ValidationError("Readers cannot publish Newsletters."
                                          )

    def save(self, *args, **kwargs):
        """Overrides model save to trigger full clean pass loops on updates."""
        if self.pk is not None:
            self.full_clean()
        super().save(*args, **kwargs)


class Publisher(models.Model):
    """
    Represents a media network publication. Supports multi-editor management
    and multi-journalist content posting assignments.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    editors = models.ManyToManyField(
        User, related_name='assigned_publishers',
        limit_choices_to={'role': 'editor'})
    journalists = models.ManyToManyField(
        User, related_name='allowed_publishers',
        limit_choices_to={'role': 'journalist'})

    def __str__(self):
        return self.name


class Article(models.Model):
    """
    Represents a news story submitted to a publisher by an assigned
    journalist. Requires review and validation from an assigned editor
    before going live. The `approved` flag tracks editorial sign-off,
    and `created_at` records when the story was first filed.
    """
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='published_articles')
    publisher = models.ForeignKey(Publisher, on_delete=models.SET_NULL,
                                  related_name='articles',
                                  null=True, blank=True)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        """Automates string parameter conversion to populate empty
        slug entries."""
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Newsletter(models.Model):
    """
    Represents a curated digest compiled by an assigned journalist from a
    selection of existing Articles. Requires structural approval checks
    from assigned editors before dispatching. `created_at` records when
    the bulletin was first compiled.
    """
    STATUS_CHOICES = [
        ('draft', 'Pending Review'),
        ('approved', 'Approved for Dispatch'),
    ]
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    articles = models.ManyToManyField(
        Article, related_name='newsletters', blank=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='published_newsletters')
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE,
                                  related_name='newsletters')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES,
                              default='draft')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
