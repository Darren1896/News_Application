# LightFeed — News_Application

A Django news platform where Readers, Journalists, and Editors collaborate on
articles and newsletters. Readers can follow publishers and journalists;
journalists can write articles independently or under a publisher; editors
manage publishers, staff assignments, and approvals.

## Features

### Reader
- Browse published articles and dispatched newsletters
- View registered publishers and journalists
- Follow/unfollow publishers and journalists to build a personalized feed

### Journalist
- Write articles, either assigned to a publisher or published independently
- Edit or delete their own articles and newsletters
- Compose newsletters by curating a selection of their own approved articles

### Editor
- Create publishers and assign editors/journalists to them
- Approve articles and newsletters for publication
- Edit or delete any article or newsletter

### Dashboard
The main dashboard groups related actions behind four hubs — **News Feed**,
**Publishers**, **Articles**, **Newsletters** — instead of showing every
action at once, with each hub showing only the actions relevant to the
logged-in user's role.

## Tech Stack

- **Backend:** Django 6.0, Django REST Framework
- **Database:** MySQL 8.0
- **Auth:** Django's built-in auth with a custom `User` model (`role` field:
  reader / journalist / editor) and DRF Token Authentication for the API
- **Containerization:** Docker, docker-compose

## Project Structure

```
News_Application/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── manage.py
├── News_Application/        # Project settings, root urls.py, wsgi.py
└── LightFeed/                # Main app
    ├── models.py             # User, Publisher, Article, Newsletter, ResetToken
    ├── views.py               # Standard Django views (HTML pages)
    ├── api_views.py           # DRF ViewSets
    ├── serializers.py         # DRF serializers
    ├── permissions.py         # DRF custom permission classes
    ├── urls.py
    ├── tests.py
    └── templates/             # All app templates (flat, no namespace folder)
```

## Data Model Summary

- **User** — extends `AbstractUser`, adds `role` (reader/journalist/editor),
  `subscribed_publishers` (M2M → Publisher), `subscribed_journalists`
  (M2M → self, asymmetric)
- **Publisher** — `editors` and `journalists` (M2M → User, role-restricted)
- **Article** — `author` (FK → User), `publisher` (FK → Publisher, optional —
  supports independent publishing), `approved` (bool), `created_at`
- **Newsletter** — `author` (FK → User), `publisher` (FK → Publisher,
  required), `articles` (M2M → Article — a newsletter is a curated digest of
  the author's own approved articles), `description`, `status`, `created_at`
- **ResetToken** — password reset tokens tied to a `User`

## Running with Docker (recommended)

1. Make sure Docker and docker-compose are installed.
2. From the project root (same level as `manage.py`):
   ```bash
   docker-compose up --build
   ```
   The first run will take longer — MySQL needs to initialize a fresh
   data volume, and `web` will wait for it to be ready before starting.
3. In a second terminal, apply migrations:
   ```bash
   docker-compose exec web python manage.py migrate
   ```
4. Visit **http://localhost:8000**

To stop:
```bash
docker-compose down
```

To stop and wipe the database volume (start completely fresh):
```bash
docker-compose down -v
```

### Services

| Service | Image           | Port  | Notes                                   |
|---------|-----------------|-------|------------------------------------------|
| `web`   | built from `Dockerfile` | 8000  | Django dev server, waits for `db` to be reachable before starting |
| `db`    | `mysql:8.0`     | 3306  | Data persisted in a named volume (`db_data`) |

## Running Locally (without Docker)

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Make sure a MySQL server is running locally and matches the credentials
   in `News_Application/settings.py` (`DATABASES`). Note that `settings.py`
   currently points `HOST` at `db`, the docker-compose service name — for
   local (non-Docker) runs, change this to `localhost` (or your DB host).
3. Apply migrations and run the server:
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

## Running Tests

```bash
docker-compose exec web python manage.py test LightFeed
```

(or, outside Docker: `python manage.py test LightFeed`)

## API

The DRF API is available under `/api/`, including:
- `GET/POST /api/articles/` — list published articles / create a draft (journalists only)
- `GET /api/articles/subscribed/` — feed of articles from followed publishers/journalists
- `POST /api/token/` or `/api/login/` — obtain an auth token

API requests use Token Authentication: include `Authorization: Token <your-token>`.
