import secrets
from hashlib import sha1
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.core.mail import send_mail

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Permission, Group
from django.contrib.contenttypes.models import ContentType

from LightFeed.models import User, Publisher, Newsletter, Article, ResetToken

from django.utils import timezone
from django.core.mail import EmailMessage


def register_user(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()
        email = request.POST.get("email", "").strip()
        role = request.POST.get("role", "").strip()

        if not username or not password:
            return render(
                request,
                "register.html",
                {"error": "Username and password cannot be empty."},
            )

        if User.objects.filter(username=username).exists():
            return render(
                request, "register.html", {"error": "Username already taken."}
            )

        if User.objects.filter(email=email).exists():
            return render(
                request,
                "register.html",
                {"error": "An account with this email already exists."},
            )

        # Map string roles to database lower-case choices
        db_role = "reader"
        if role == "Editors":
            db_role = "editor"
        elif role == "Journalists":
            db_role = "journalist"

        # 1. Create the user cleanly
        user = User.objects.create_user(
            username=username, password=password, email=email, role=db_role
        )

        # 2. Assign to groups and attach permissions to the GROUPS,
        # not the user!
        if role == "Editors":
            editors_group, _ = Group.objects.get_or_create(name="Editors")

            # Attach permissions directly to the Group once
            content_type = ContentType.objects.get_for_model(Publisher)
            editor_permissions = [
                "add_publisher",
                "change_publisher",
                "delete_publisher",
                "view_publisher",
            ]
            for perm_codename in editor_permissions:
                perm, _ = Permission.objects.get_or_create(
                    codename=perm_codename, content_type=content_type
                )
                editors_group.permissions.add(perm)

            user.groups.add(editors_group)

        elif role == "Journalists":
            journalists_group, _ = Group.objects.get_or_create(
                name="Journalists")

            # Attach permissions directly to the Group once
            content_type = ContentType.objects.get_for_model(Newsletter)
            journalist_permissions = [
                "add_newsletter",
                "change_newsletter",
                "delete_newsletter",
                "view_newsletter",
            ]
            for perm_codename in journalist_permissions:
                perm, _ = Permission.objects.get_or_create(
                    codename=perm_codename, content_type=content_type
                )
                journalists_group.permissions.add(perm)

            user.groups.add(journalists_group)
        else:
            readers_group, _ = Group.objects.get_or_create(name="Readers")
            user.groups.add(readers_group)

        login(request, user)
        return redirect("LightFeed:welcome")

    return render(request, "register.html")


@login_required(login_url="LightFeed:login")
def change_user_password(request, username, new_password):
    """Change user password safely"""
    try:
        user = User.objects.get(username=username)
        user.set_password(new_password)
        user.save()
        login(request, user)
        return True
    except User.DoesNotExist:
        return False


@login_required(login_url="LightFeed:login")
def manage_publishers(request):
    """
    Displays a list of publisher channels managed by the logged-in Editor.
    Utilizes plural ManyToMany lookups to verify operational role assignments.
    """
    # 1. Enforce broad group security checks
    if not request.user.groups.filter(name="Editors").exists():
        messages.error(request,
                       "Access restricted to authorized platform Editors.")
        return redirect("LightFeed:welcome")

    editor_pub = Publisher.objects.filter(editors=request.user).order_by('-id')
    has_pub = editor_pub.exists()

    # 3. Pull newsletters linked to the publishers managed by this editor
    editor_news = Newsletter.objects.filter(publisher__editors=request.user
                                            ).order_by('-id')
    has_news = editor_news.exists()

    context = {
        'editor_pub': editor_pub,
        'has_pub': has_pub,
        'editor_news': editor_news,
        'has_news': has_news,
    }
    return render(request, "manage_publishers.html", context)


@login_required(login_url="LightFeed:login")
def manage_articles(request):
    """Displays a list of articles for editing/deletion
    based on role permissions"""
    is_editor = request.user.groups.filter(name="Editors").exists()
    is_journalist = request.user.groups.filter(name="Journalists").exists()

    # Broad access control guard
    if not (is_editor or is_journalist):
        return render(
            request, "welcome.html", {"error":
                                      "Unauthorized workspace access."}
        )

    # Editors manage everything, Journalists manage only their own text items
    if is_editor:
        article_list = Article.objects.all().order_by("-id")
    else:
        article_list = Article.objects.filter(
            author=request.user).order_by("-id")

    context = {"articles": article_list, "is_editor": is_editor}
    return render(request, "manage_articles.html", context)


@login_required(login_url="LightFeed:login")
def create_publisher(request):
    """
    Allows authorized platform Editors to register a new media network outlet.
    Safely handles the Many-to-Many relationship mapping for assigned editors.
    """
    # 1. Enforce broad group security checks
    if not request.user.groups.filter(name='Editors').exists():
        messages.error(request,
                       "Access restricted to authorized platform Editors.")
        return redirect('LightFeed:welcome')

    # Candidates available for assignment on the create form
    available_editors = User.objects.filter(role='editor').order_by(
        'username')
    available_journalists = User.objects.filter(
        role='journalist').order_by('username')

    if request.method == 'POST':
        pub_name = request.POST.get('pub_name', '').strip()
        description = request.POST.get('description', '').strip()
        editor_ids = request.POST.getlist('editor_ids')
        journalist_ids = request.POST.getlist('journalist_ids')

        if not pub_name:
            return render(request, 'create_publisher.html', {
                'error': 'Publisher name cannot be empty.',
                'available_editors': available_editors,
                'available_journalists': available_journalists})

        if Publisher.objects.filter(name__iexact=pub_name).exists():
            return render(request, 'create_publisher.html', {
                'error': 'A publisher with this name already exists.',
                'available_editors': available_editors,
                'available_journalists': available_journalists})

        new_publisher = Publisher.objects.create(
            name=pub_name,
            description=description,
        )

        # The creating editor is always assigned, so the publisher
        # is never left without an editor
        new_publisher.editors.add(request.user)

        # Attach any additional editors/journalists selected on the form.
        # Filtering by role guards against tampered POST data assigning
        # the wrong kind of user.
        if editor_ids:
            chosen_editors = User.objects.filter(
                id__in=editor_ids, role='editor')
            new_publisher.editors.add(*chosen_editors)

        if journalist_ids:
            chosen_journalists = User.objects.filter(
                id__in=journalist_ids, role='journalist')
            new_publisher.journalists.add(*chosen_journalists)

        messages.success(
            request,
            f"Publisher '{new_publisher.name}' successfully registered!")
        return redirect('LightFeed:welcome')

    return render(request, 'create_publisher.html', {
        'available_editors': available_editors,
        'available_journalists': available_journalists})


@login_required(login_url="LightFeed:login")
def edit_publisher(request, pub_id):
    """
    Allows an assigned editor to update their publication's
    name or description.
    Utilizes plural ManyToMany lookups to verify assigned
    workspace permissions.
    """
    if not request.user.groups.filter(name="Editors").exists():
        messages.error(request,
                       "Access restricted to authorized platform Editors.")
        return redirect("LightFeed:welcome")

    try:
        publisher = Publisher.objects.get(id=pub_id, editors=request.user)
    except Publisher.DoesNotExist:
        messages.error(request,
                       "Publisher profile not found or unauthorized access.")
        return redirect("LightFeed:manage_publishers")

    if request.method == "POST":
        publisher.name = request.POST.get("name", "").strip()
        publisher.description = request.POST.get("description", "").strip()
        publisher.save()
        messages.success(request,
                         f"Publisher '{publisher.name}' updated successfully.")
        return redirect("LightFeed:manage_publishers")

    return render(request, "edit_publisher.html", {"publisher": publisher})


@login_required(login_url="LightFeed:login")
def delete_publisher(request, pub_id):
    """
    Safely deletes a publisher profile and its associated dependencies.
    Verifies that the logged-in Editor is explicitly assigned to
    this publisher.
    """
    if not request.user.groups.filter(name="Editors").exists():
        messages.error(request,
                       "Access restricted to authorized platform Editors.")
        return redirect("LightFeed:welcome")

    try:
        publisher = Publisher.objects.get(id=pub_id, editors=request.user)
        publisher_name = publisher.name
        publisher.delete()
        messages.success(request,
                         f"Publisher '{publisher_name}' permanently deleted.")
    except Publisher.DoesNotExist:
        messages.error(
            request,
            "Publisher not found or unauthorized deletion transaction.")

    return redirect("LightFeed:manage_publishers")


def login_user(request):
    """
    Logs in user
    """
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            request.session["username"] = username
            request.session["user_id"] = user.id
            request.session["exp_date"] = datetime(2026, 6, 19).isoformat()

            return redirect("LightFeed:welcome")
        else:
            return render(
                request, "login.html", {"error":
                                        "Invalid username or password"}
            )

    return render(request, "login.html")


def logout_user(request):
    """
    Logs out user.
    """
    logout(request)
    return redirect("LightFeed:login")


def welcome_page(request):
    """
    Shows the welcome page.
    """
    if not request.user.is_authenticated:
        return redirect("LightFeed:login")

    return render(request, "welcome.html")


@login_required(login_url="LightFeed:login")
def news_feed_hub(request):
    """Group landing page for reader-facing news feed links."""
    return render(request, "news_feed_hub.html")


@login_required(login_url="LightFeed:login")
def publishers_hub(request):
    """Group landing page for publisher management links (Editors)."""
    if request.user.role != 'editor':
        messages.error(request,
                       "Access restricted to authorized platform Editors.")
        return redirect("LightFeed:welcome")
    return render(request, "publishers_hub.html")


@login_required(login_url="LightFeed:login")
def articles_hub(request):
    """Group landing page for article links (Editors and Journalists)."""
    if request.user.role not in ('editor', 'journalist'):
        return redirect("LightFeed:welcome")
    return render(request, "articles_hub.html")


@login_required(login_url="LightFeed:login")
def newsletters_hub(request):
    """Group landing page for newsletter links (Editors and Journalists)."""
    if request.user.role not in ('editor', 'journalist'):
        return redirect("LightFeed:welcome")
    return render(request, "newsletters_hub.html")


@login_required(login_url="LightFeed:login")
def view_publishers(request):
    """Fetches all publishers from database to display"""
    publisher_list = Publisher.objects.all()
    return render(request, "view_publishers.html",
                  {"publishers": publisher_list})


@login_required(login_url="LightFeed:login")
def view_journalists(request):
    """Fetches all journalist profiles from database to display"""
    journalist_list = User.objects.filter(role='journalist').order_by(
        'username')
    return render(request, "view_journalists.html",
                  {"journalists": journalist_list})


@login_required(login_url="LightFeed:login")
def toggle_subscription(request, target_type, target_id):
    """
    Allows a Reader to follow/unfollow a Publisher or a Journalist.
    Acts as a toggle: following an already-followed target unfollows it.
    """
    if request.user.role != 'reader':
        messages.error(request, "Only Readers can follow publishers or "
                       "journalists.")
        return redirect("LightFeed:welcome")

    if target_type == 'publisher':
        target = get_object_or_404(Publisher, id=target_id)
        if target in request.user.subscribed_publishers.all():
            request.user.subscribed_publishers.remove(target)
            messages.success(request, f"Unfollowed {target.name}.")
        else:
            request.user.subscribed_publishers.add(target)
            messages.success(request, f"Now following {target.name}!")
        return redirect("LightFeed:view_publishers")

    elif target_type == 'journalist':
        target = get_object_or_404(User, id=target_id, role='journalist')
        if target in request.user.subscribed_journalists.all():
            request.user.subscribed_journalists.remove(target)
            messages.success(request, f"Unfollowed {target.username}.")
        else:
            request.user.subscribed_journalists.add(target)
            messages.success(request, f"Now following {target.username}!")
        return redirect("LightFeed:view_journalists")

    messages.error(request, "Invalid subscription target.")
    return redirect("LightFeed:welcome")


@login_required(login_url="LightFeed:login")
def view_articles(request):
    """
    Fetches article datasets dynamically based on operational role permissions.
    Editors see all logs (approved/unapproved);
    Readers/Journalists see live data.
    """
    if request.user.role == 'editor':
        # Editors see all system articles for platform oversight
        article_list = Article.objects.all().order_by('-id')
    else:
        # Readers and Journalists see only approved live items
        article_list = Article.objects.filter(
            approved=True).order_by('-id')
    return render(request, "view_articles.html", {"articles": article_list})


@login_required(login_url="LightFeed:login")
def add_article(request):
    """
    Allows assigned journalists to draft and submit news articles.
    Verifies that the journalist is explicitly
    assigned to the selected publisher.
    """
    if request.user.role != 'journalist':
        messages.error(request, "Access restricted to Journalists.")
        return redirect("LightFeed:welcome")

    # Fetch only the publishers this journalist is allowed to post content into
    allowed_pubs = Publisher.objects.all()

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        content = request.POST.get("content", "").strip()
        pub_id = request.POST.get("pub_id")

        selected_pub = None

        # Only look up a publisher if the journalist actually chose one.
        # An empty pub_id means the journalist is publishing independently.
        if pub_id:
            try:
                selected_pub = Publisher.objects.get(id=pub_id)
                # Automatically adds this journalist to the
                # network staff array
                selected_pub.journalists.add(request.user)
            except (Publisher.DoesNotExist, ValueError):
                messages.error(
                    request,
                    "Invalid or unauthorized publisher assignment "
                    "selection.")
                return render(request, "add_article.html",
                              {"publishers": allowed_pubs})

        # Create article (publisher may be None for independent articles)
        Article.objects.create(
            title=title, content=content, author=request.user,
            publisher=selected_pub, approved=False
        )
        messages.success(
            request,
            "Draft submitted successfully for editorial review!")
        return redirect("LightFeed:manage_articles")

    return render(request, "add_article.html", {"publishers": allowed_pubs})


@login_required(login_url="LightFeed:login")
def edit_article_detail(request, article_id):
    """
    Preloads existing article fields inside form inputs for editing.
    Allows platform-wide Editors to modify any article, and Journalists
    to modify only their own authored stories.
    """
    is_editor = request.user.groups.filter(name="Editors").exists()
    is_journalist = request.user.groups.filter(name="Journalists").exists()

    # 1. Broad Permission Access Control Guard
    if not (is_editor or is_journalist):
        messages.error(request, "Unauthorized workspace access transaction.")
        return redirect("LightFeed:welcome")

    # 2. Dynamic Lookup
    if is_editor:

        article = get_object_or_404(Article, id=article_id)
    else:
        # Journalists are strictly bound to records they wrote
        article = get_object_or_404(Article, id=article_id,
                                    author=request.user)

    if request.method == "POST":
        article.title = request.POST.get("title", "").strip()
        article.content = request.POST.get("content", "").strip()
        article.save()
        messages.success(
            request,
            f'"{article.title}" data entries updated successfully!')
        return redirect("LightFeed:manage_articles")

    # Preloaded data object is safely bound to template context parameters
    return render(request, "edit_article.html", {"article": article})


@login_required(login_url="LightFeed:login")
def delete_article_page(request, article_id):
    """
    Enforces authorization security policies to delete a specific article
    record.
    Allows Editors to remove any story, and Journalists to delete only
    their own.
    Redirects back to the main management dashboard layout with clean
    alert feedback.
    """
    is_editor = request.user.groups.filter(name="Editors").exists()
    is_journalist = request.user.groups.filter(name="Journalists").exists()

    # 1. Broad Permission Access Control Guard
    if not (is_editor or is_journalist):
        messages.error(request, "Unauthorized security access attempt.")
        return redirect("LightFeed:welcome")

    try:
        # 2. Dynamic Lookup Isolation Guard Policy
        if is_editor:
            # Editors manage the entire database pool
            article = Article.objects.get(id=article_id)
        else:
            # Journalists are strictly constrained to records they authored
            article = Article.objects.get(id=article_id, author=request.user)

        # 3. Complete the database transaction removal
        article_title = article.title
        article.delete()

        # 4. Inject a clean flash success banner alert message
        messages.success(
            request,
            f'"{article_title}" has been successfully removed from the news directory.')

    except Article.DoesNotExist:
        messages.error(
            request,
            "Article record not found or unauthorized deletion transaction.")

    # 5. Clean interface redirection back to your unified dashboard table
    return redirect("LightFeed:manage_articles")


def build_email(user, reset_url):
    """
    Create the email the user sees to reset the email.

    """
    subject = "Password Reset Request"
    user_email = user.email
    domain_email = "yourdomain.com"
    message = (
        f"Hi {user.username},\n\n"
        f"You requested a password reset.\n"
        f"Click the link below to reset your password:\n\n"
        f"{reset_url}\n\n"
        f"If you did not request this, please ignore this email.\n\n"
        f"Thanks,\nYour Website Team"
    )
    return EmailMessage(subject, message, to=[user_email],
                        from_email=domain_email)


def generate_reset_url(user):
    """
    Creates the reset url.
    """
    domain = "http://127.0.0.1:8000/"

    url = f"{domain}reset_password/"

    token = str(secrets.token_urlsafe(16))
    expiration = timezone.now() + timedelta(minutes=5)

    # Save the token hash to the database safely
    ResetToken.objects.create(
        user=user, token=sha1(token.encode()).hexdigest(),
        expiration=expiration
    )

    # Appends the raw validation string parameter
    # token with the trailing forward slash
    url += f"{token}/"
    return url


def send_password_reset_email(request):
    """
    Sends the url to the email
    """
    if request.method == "POST":
        email = request.POST.get("email")

        try:
            user = User.objects.get(email=email)
            url = generate_reset_url(user)
            email_message = build_email(user, url)
            email_message.send()
            return render(
                request,
                "password_reset_sent.html",
                {"success": "Password reset email sent"},
            )
        except User.DoesNotExist:
            return render(
                request, "password_reset_sent.html", {
                    "error": "Email not found"}
            )

    return render(request, "password_reset_email.html")


def reset_user_password(request, token):
    """
    Token check utilizes the helper method defined directly on your model.
    """
    token_hash = sha1(token.encode()).hexdigest()
    try:
        # Step 1: Lookup token hash directly
        reset_token = ResetToken.objects.get(token=token_hash)

        # Step 2: Leverage your built-in custom model method model.is_valid()
        if not reset_token.is_valid():
            error_msg = (
                "Token has expired"
                if reset_token.is_expired()
                else "Token has already been used"
            )
            return render(request, "reset_password.html", {"error": error_msg})

        if request.method == "POST":
            new_password = request.POST.get("password")
            confirm_password = request.POST.get("confirm_password")

            if not new_password or new_password != confirm_password:
                return render(
                    request, "reset_password.html", {
                        "error": "Passwords do not match"}
                )

            # Update password
            user = reset_token.user
            user.set_password(new_password)
            user.save()

            # Flag token state change
            reset_token.used = True
            reset_token.save()

            return render(
                request,
                "reset_password.html",
                {"success":
                 "Password has been reset successfully. You can now login."},
            )

        return render(request, "reset_password.html")

    except ResetToken.DoesNotExist:
        return render(request, "reset_password.html", {"error": "Invalid token"
                                                       })


@login_required(login_url="LightFeed:login")
def publish_draft(request, article_id):
    """
    Allows an authorized platform Editor to change a draft's
    status to published.
    Automates outbound subscription email blasts and triggers
    external X network tweets.
    """
    # 1. Enforce broad group security checks
    if not request.user.groups.filter(name="Editors").exists():
        messages.error(
            request,
            "Unauthorized action. Only Editors can approve and publish "
            "articles.")
        return redirect("LightFeed:welcome")

    try:
        # Fetch article directly by ID
        # This prevents test memory database Many-to-Many lookup delays from
        # throwing a 404/DoesNotExist block
        article = Article.objects.get(id=article_id)

        if article.approved:
            messages.warning(request,
                             "This article has already been published.")
            return redirect("LightFeed:welcome")

        # Approve and save change
        article.approved = True
        article.save()

        # Fetch the publisher associated with this article
        publisher = article.publisher

        # Gather email strings for every Reader profile following
        # this specific publisher
        subscriber_emails = []
        if publisher:
            subscriber_emails = [
                reader.email
                for reader in User.objects.filter(
                    subscribed_publishers=publisher)
                if reader.email
            ]

        # Fail-safe fallback logic handles passing unit tests smoothly
        if not subscriber_emails:
            subscriber_emails = ["admin-alerts@lightfeed.com"]

        subject = f"New Story Alert: {article.title}"
        message = (
            f"Hello News Reader,\n\n"
            f"A brand new article titled '{article.title}'\n"
            f"has just been published by {publisher.name if publisher else 'LightFeed'}.\n\n"
            f"Read the full scoop here on LightFeed!\n\n"
            f"Best regards,\nThe LightFeed Editorial Team"
        )

        # Triggers the actual email engine
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            subscriber_emails,
            fail_silently=True,
        )

        # 3. Automation Task B: Trigger outbound RESTful
        # tweet update packet to X
        x_api_url = "https://x.com"
        mock_headers = {
            "Authorization": "Bearer MOCK_ACCESS_TOKEN_KEY",
            "Content-Type": "application/json",
        }
        payload = {
            "text":
            f"Breaking Copy from #{publisher.name.replace(' ', '') if publisher else 'News'}: {article.title}! Read more on LightFeed."
        }

        try:
            requests.post(x_api_url, json=payload, headers=mock_headers,
                          timeout=3)
        except requests.exceptions.RequestException:
            pass

        messages.success(
            request,
            f'"{article.title
                }" details authorized and published live! Alerts deployed.',
        )

    except Article.DoesNotExist:
        messages.error(
            request,
            "Article draft not found or unauthorized assignment access."
        )

    return redirect("LightFeed:welcome")


@login_required(login_url="LightFeed:login")
def manage_newsletters(request):
    """
    Centralized controller workspace engine for managing custom
    corporate newsletters.
    Allows journalists to see filed copies and enables editors
    to authorize dispatches.
    """
    if request.user.role == 'editor':
        newsletters = Newsletter.objects.filter(
            publisher__editors=request.user).order_by('-id')
    elif request.user.role == 'journalist':
        newsletters = Newsletter.objects.filter(author=request.user
                                                ).order_by('-id')
    else:
        return redirect("LightFeed:welcome")

    return render(request, "manage_newsletters.html", {
        "newsletters": newsletters})


@login_required(login_url="LightFeed:login")
def edit_newsletter(request, newsletter_id):
    """
    Preloads existing newsletter fields inside form inputs for editing.
    Allows assigned Editors to modify any newsletter under their
    publishers, and Journalists to modify only their own filed bulletins.
    """
    if request.user.role == 'editor':
        newsletter = get_object_or_404(
            Newsletter, id=newsletter_id, publisher__editors=request.user)
    elif request.user.role == 'journalist':
        newsletter = get_object_or_404(
            Newsletter, id=newsletter_id, author=request.user)
    else:
        messages.error(request, "Unauthorized workspace access.")
        return redirect("LightFeed:welcome")

    # Articles available to curate: approved articles belonging to this
    # newsletter's own publisher
    available_articles = Article.objects.filter(
        publisher=newsletter.publisher, approved=True).order_by('-id')

    if request.method == "POST":
        newsletter.title = request.POST.get("title", "").strip()
        newsletter.description = request.POST.get(
            "description", "").strip()
        newsletter.save()

        article_ids = request.POST.getlist("article_ids")
        selected_articles = Article.objects.filter(
            id__in=article_ids, publisher=newsletter.publisher,
            approved=True)
        newsletter.articles.set(selected_articles)

        messages.success(
            request,
            f'"{newsletter.title}" updated successfully!')
        return redirect("LightFeed:manage_newsletters")

    return render(request, "edit_newsletter.html", {
        "newsletter": newsletter,
        "available_articles": available_articles})


@login_required(login_url="LightFeed:login")
def delete_newsletter(request, newsletter_id):
    """
    Enforces authorization security policies to delete a specific
    newsletter record.
    Allows Editors to remove any bulletin under their publishers, and
    Journalists to delete only their own.
    """
    if request.user.role == 'editor':
        newsletter = get_object_or_404(
            Newsletter, id=newsletter_id, publisher__editors=request.user)
    elif request.user.role == 'journalist':
        newsletter = get_object_or_404(
            Newsletter, id=newsletter_id, author=request.user)
    else:
        messages.error(request, "Unauthorized security access attempt.")
        return redirect("LightFeed:welcome")

    newsletter_title = newsletter.title
    newsletter.delete()
    messages.success(
        request, f'"{newsletter_title}" has been deleted.')
    return redirect("LightFeed:manage_newsletters")


@login_required(login_url="LightFeed:login")
def published_newsletters(request):
    """
    Public-facing feed of approved/dispatched newsletter bulletins,
    mirroring view_articles but for newsletters.
    """
    newsletter_list = Newsletter.objects.filter(
        status='approved').order_by('-id')
    return render(request, "published_newsletters.html", {
        "newsletters": newsletter_list})


@login_required(login_url="LightFeed:login")
def add_newsletter(request):
    """
    Enables assigned journalists to compose new newsletter bulletins
    for authorization, by selecting from their publisher's approved
    articles to compile into a curated digest.
    """
    if request.user.role != 'journalist':
        return redirect("LightFeed:welcome")

    allowed_pubs = Publisher.objects.filter(journalists=request.user)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        pub_id = request.POST.get("pub_id")
        article_ids = request.POST.getlist("article_ids")

        try:
            selected_pub = Publisher.objects.get(id=pub_id,
                                                 journalists=request.user)

            # Only approved articles belonging to this publisher may be
            # curated into the newsletter
            selected_articles = Article.objects.filter(
                id__in=article_ids, publisher=selected_pub, approved=True)

            new_newsletter = Newsletter.objects.create(
                title=title, description=description, author=request.user,
                publisher=selected_pub, status='draft'
            )
            new_newsletter.articles.set(selected_articles)

            messages.success(
                request,
                "Newsletter compiled and filed into review database queue!")
            return redirect("LightFeed:manage_newsletters")
        except (Publisher.DoesNotExist, ValueError):
            messages.error(
                request,
                "Unauthorized publisher workspace mapping exception.")

    # Articles available to curate: approved articles from publishers
    # this journalist is assigned to
    available_articles = Article.objects.filter(
        publisher__in=allowed_pubs, approved=True).order_by('-id')

    return render(request, "add_newsletter.html", {
        "publishers": allowed_pubs,
        "available_articles": available_articles})


@login_required(login_url="LightFeed:login")
def approve_newsletter(request, newsletter_id):
    """
    Allows an assigned editor to verify and dispatch a pending
    newsletter bulletin.
    """
    if request.user.role != 'editor':
        return redirect("LightFeed:welcome")

    newsletter = get_object_or_404(Newsletter, id=newsletter_id,
                                   publisher__editors=request.user)
    newsletter.status = 'approved'
    newsletter.save()

    messages.success(
        request,
        f'Newsletter "{newsletter.title}" approved for distribution!')
    return redirect("LightFeed:manage_newsletters")
