from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token as AuthToken
from .models import User, Publisher, Article, Newsletter


class LightFeedAPITestSuite(APITestCase):
    """
    Automated test engine validating role-based authorization parameters,
    isolated subscription filters, newsletter storage integrity, and Option 2
    post-approval background webhook delivery automation pipelines.
    """

    def setUp(self):
        """Set up standardized, role-isolated test configurations
        and database entities."""
        # 1. Instantiate Authorization Group Framework Nodes
        self.readers_group, _ = Group.objects.get_or_create(name="Readers")
        self.journalists_group, _ = Group.objects.get_or_create(
            name="Journalists")
        self.editors_group, _ = Group.objects.get_or_create(name="Editors")

        # 2. Instantiate Base Model Profiles
        self.reader = User.objects.create_user(
            username="test_reader", password="pwd", email="r@test.com",
            role="reader")
        self.journalist = User.objects.create_user(
            username="test_journ", password="pwd", email="j@test.com",
            role="journalist")
        self.editor = User.objects.create_user(
            username="test_editor", password="pwd", email="e@test.com",
            role="editor")

        self.reader.groups.add(self.readers_group)
        self.journalist.groups.add(self.journalists_group)
        self.editor.groups.add(self.editors_group)

        # 3. Secure Core API Authentication Bearer Tokens
        self.reader_token = AuthToken.objects.create(user=self.reader)
        self.journ_token = AuthToken.objects.create(user=self.journalist)
        self.editor_token = AuthToken.objects.create(user=self.editor)

        # 4. Instantiate Publishers
        self.publisher_alpha = Publisher.objects.create(
            name="Alpha News", description="Main Corporate Outlet")
        self.publisher_beta = Publisher.objects.create(
            name="Beta News", description="Secondary Niche Outlet")

        # Map multi-user assignments using Many-to-Many helper methods
        self.publisher_alpha.editors.add(self.editor)
        self.publisher_alpha.journalists.add(self.journalist)
        self.publisher_beta.editors.add(self.editor)
        self.publisher_beta.journalists.add(self.journalist)

        # 5. Instantiate Articles containing explicitly
        # isolated clean unique URL slugs
        self.article_published = Article.objects.create(
            title="Published Story Alpha",
            slug="published-story-alpha",
            content="Breaking news production copy.",
            author=self.journalist,
            publisher=self.publisher_alpha,
            approved=True
        )
        self.article_draft = Article.objects.create(
            title="Pending Draft Beta",
            slug="pending-draft-beta",
            content="Work in progress editorial framework.",
            author=self.journalist,
            publisher=self.publisher_beta,
            approved=False
        )

        # 6. Instantiate Newsletters assigned to a specific publisher
        # workspace, curated from existing approved articles
        self.newsletter = Newsletter.objects.create(
            title="Weekly Pulse",
            description="Digest copy layout text.",
            author=self.journalist,
            publisher=self.publisher_alpha,
            status="draft"
        )
        self.newsletter.articles.add(self.article_published)

        # 7. Reverse Endpoint Mapping Signatures
        self.list_url = reverse('LightFeed:article-list')
        self.subscribed_url = reverse('LightFeed:article-subscribed-feed')
        self.detail_url = lambda pk: reverse('LightFeed:article-detail',
                                             kwargs={'pk': pk})

    # =====================================================================
    # ROLE MANAGEMENT TESTS
    # =====================================================================
    def test_unauthenticated_access_fails(self):
        """FAIL CASE: Assures traffic without credentials
        receives an HTTP 401 response."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reader_retrieve_all_published_only(self):
        """SUCCESS CASE: Assures readers can only
        view live approved publications."""
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.reader_token.key)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should count the single live story block, ignoring unapproved drafts
        self.assertEqual(len(response.data), 1)

    def test_reader_subscribed_feed_isolation(self):
        """SUCCESS CASE: Readers isolate
        streams matching their followed sources."""
        self.reader.subscribed_publishers.add(self.publisher_alpha)

        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.reader_token.key)
        response = self.client.get(self.subscribed_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_subscribed_feed_includes_followed_journalists_independent_work(
            self):
        """SUCCESS CASE: Following a journalist (not a publisher) should
        still surface that journalist's independently-published articles,
        confirming the independent-publishing and follow features work
        together correctly."""
        independent_article = Article.objects.create(
            title="Independent Followed Story",
            slug="independent-followed-story",
            content="No publisher attached.",
            author=self.journalist,
            publisher=None,
            approved=True
        )

        self.reader.subscribed_journalists.add(self.journalist)

        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.reader_token.key)
        response = self.client.get(self.subscribed_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_titles = [item["title"] for item in response.data]
        self.assertIn(independent_article.title, returned_titles)

    def test_journalist_can_create_article(self):
        """SUCCESS CASE: Journalist uploads content,
        defaulting fields to draft."""
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.journ_token.key)
        payload = {
            "title": "New Global Breakthrough",
            "content": "Scientists document...",
            "publisher": self.publisher_alpha.id
        }
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Article.objects.filter(
            title="New Global Breakthrough").count(), 1)
        self.assertEqual(Article.objects.get(
            title="New Global Breakthrough").approved, False)

    def test_journalist_can_publish_independently(self):
        """SUCCESS CASE: Journalist submits an article with no publisher
        assigned at all, confirming independent publishing works end
        to end through the API (not just the model layer)."""
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.journ_token.key)
        payload = {
            "title": "Independent Investigation",
            "content": "Filed without any publisher backing.",
        }
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        created = Article.objects.get(title="Independent Investigation")
        self.assertIsNone(created.publisher)
        self.assertEqual(created.approved, False)

    def test_reader_cannot_create_article(self):
        """FAIL CASE: Assures regular accounts cannot inject
        stories into the directory."""
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.reader_token.key)
        payload = {"title": "Illegal Headline", "content": "Context",
                   "publisher": self.publisher_alpha.id}
        response = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_update_article_attributes(self):
        """SUCCESS CASE: System editors hold universal
        oversight capabilities."""
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.editor_token.key)
        payload = {
            "title": "Approved Title Beta Change",
            "content": "Updated verified production body copy.",
            "publisher": self.publisher_beta.id
        }
        response = self.client.put(self.detail_url(self.article_draft.id),
                                   payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.article_draft.refresh_from_db()
        self.assertEqual(self.article_draft.title, "Approved Title Beta Change"
                         )

    # =====================================================================
    # NEWSLETTER TESTING
    # =====================================================================
    def test_newsletter_integrity_constraints(self):
        """SUCCESS CASE: Assures newsletter models map properties cleanly."""
        self.assertEqual(self.newsletter.title, "Weekly Pulse")
        self.assertEqual(self.newsletter.status, "draft")

    # =====================================================================
    # AUTOMATION PIPELINE WEBHOOK TESTING
    # =====================================================================
    @patch('LightFeed.views.requests.post')
    @patch('LightFeed.views.send_mail')
    def test_approval_workflow_triggers_automations(self, mock_send_mail,
                                                    mock_requests_post):
        """SUCCESS CASE: View execution runs mail blasts
        and X webhook posts."""
        # 1. Reader follows publisher_beta to match the trigger criteria
        self.reader.subscribed_publishers.add(self.publisher_beta)

        # 2. Use force_login to cleanly authenticate the
        # editor account with groups
        self.client.force_login(self.editor)

        # 3. Generate the target view path URL pattern
        session_view_url = reverse(
            'LightFeed:publish_draft',
            kwargs={'article_id': self.article_draft.id})

        # 4. Perform the GET request simulation
        response = self.client.get(session_view_url)

        # 5. Check redirection flow state back to dashboard (302 Found)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

        # 6. Assert Local Email send method fired successfully
        mock_send_mail.assert_called_once()

        # 7. Assert Local Outbound POST API call out
        # to X (Twitter) was triggered
        mock_requests_post.assert_called_once()

        # 8. Check that the payload matches the target X API endpoint address
        args, kwargs = mock_requests_post.call_args
        self.assertEqual(args[0], "https://x.com")
        self.assertIn("text", kwargs['json'])
