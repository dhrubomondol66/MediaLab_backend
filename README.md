# Feed App — Django REST Backend

A Django REST Framework backend for a social feed app (Login / Register / Feed),
built to pair with a React or Next.js frontend. Covers JWT auth, public/private
posts, comments, nested replies, and a like system across all three, with data
modeling chosen to hold up as the tables grow into the millions of rows.

## Stack

- **Django 5 + Django REST Framework** — API layer
- **djangorestframework-simplejwt** — JWT authentication (access + refresh tokens)
- **SQLite** for local dev, **PostgreSQL** for production (toggle via `.env`)
- **Pillow** for image handling
- **django-cors-headers** — CORS for the separate frontend origin

## Project layout

```
backend/
├── medialab/          # settings, root urls, wsgi/asgi, exception handler
├── users/         # custom User model (email-based), register/login/me
├── feed/             # Post, Comment, Reply, Like models + API
├── manage.py
├── requirements.txt
└── .env.example
```

## Setup

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # edit SECRET_KEY etc.
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

By default `.env` uses SQLite so there's nothing else to install for local dev.
To use Postgres, set `DB_ENGINE=postgres` and fill in the `DB_*` values.

## Authentication

JWT-based, via SimpleJWT. Email is the login identifier (no separate
"username" field — matches the Register form's first name / last name / email
/ password fields).

| Endpoint | Method | Body | Notes |
|---|---|---|---|
| `/auth/register/` | POST | `first_name, last_name, email, password, password_confirm` | Public |
| `/auth/login/` | POST | `email, password` | Returns `{ access, refresh, user }` |
| `/auth/refresh/` | POST | `refresh` | Returns a new `access` token |
| `/auth/me/` | GET | — | Requires `Authorization: Bearer <access>` |

Access tokens are short-lived (15 min default); refresh tokens rotate and get
blacklisted after use, which limits the damage if one leaks. The frontend
should store the access token in memory and the refresh token in an
httpOnly cookie if you control both frontend and backend hosting, or in
memory/secure storage otherwise — avoid `localStorage` for tokens if you can,
since it's readable by any injected script (XSS).

## Feed API

All endpoints below require `Authorization: Bearer <access_token>`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/posts/` | GET | Feed — public posts + your own private posts, newest first |
| `/api/posts/` | POST | Create a post (`text`, optional `image`, `visibility: public\|private`) |
| `/api/posts/{id}/` | GET / PATCH / DELETE | Author-only for write |
| `/api/posts/{id}/like/` | POST | Toggle like/unlike |
| `/api/posts/{id}/likes/` | GET | Who liked this post (paginated) |
| `/api/posts/{id}/comments/` | GET / POST | List / add comments |
| `/api/comments/{id}/` | DELETE | Author-only |
| `/api/comments/{id}/like/` | POST | Toggle like/unlike |
| `/api/comments/{id}/likes/` | GET | Who liked this comment |
| `/api/comments/{id}/replies/` | GET / POST | List / add replies |
| `/api/replies/{id}/` | DELETE | Author-only |
| `/api/replies/{id}/like/` | POST | Toggle like/unlike |
| `/api/replies/{id}/likes/` | GET | Who liked this reply |

Pagination is **cursor-based** (`next` / `previous` URLs in the response),
not page-number based — see "Scaling to millions of posts" below for why.

## Data model & key decisions

**Visibility.** `Post.visibility` is `public` or `private`. The feed queryset
is `Q(visibility='public') | Q(visibility='private', author=request.user)` —
private posts simply never leave the database for anyone but their author.
There's no separate "followers" concept in scope here, so this two-state
model matches the spec.

**Likes as three explicit tables, not one generic table.** `PostLike`,
`CommentLike`, and `ReplyLike` each have a `unique_together(post/comment/reply, user)`
constraint. I considered a single generic `Like` table using Django's
`ContentType` framework, but decided against it: generic foreign keys can't
be indexed as tightly as a plain FK, every query needs an extra join through
`django_content_type`, and the like-counting queries that run on every single
feed render are exactly where that overhead compounds. Three small, boring,
well-indexed tables are cheaper at read time, which is what matters when the
read/write ratio is high (a feed is read far more than it's written to).

**Denormalized counters.** `Post.likes_count`, `Post.comments_count`,
`Comment.likes_count`, `Comment.replies_count`, `Reply.likes_count` are stored
directly on the parent row and updated with `F()` expressions inside a
transaction (see `feed/services.py`) whenever a like/comment/reply is added or
removed. The alternative — `COUNT(*)` over the likes table every time a post
renders — is fine at hundreds of rows and expensive at millions. The
trade-off is standard: an extra atomic `UPDATE` on write, in exchange for O(1)
reads.

**Toggle-like endpoints.** `POST /like/` toggles rather than having separate
like/unlike endpoints, matching how most feed UIs actually call it (a single
button, single click handler). The response tells you the resulting state
(`is_liked`, `likes_count`) so the frontend doesn't need a second round trip.

**"Is this liked by me?" without N+1 queries.** Rather than one `EXISTS` query
per post/comment/reply in a list response, the viewset pre-loads the current
user's full set of liked IDs once per request (`liked_post_ids`,
`liked_comment_ids`, `liked_reply_ids` — three queries total, not three times
the number of items on the page) and each serializer just checks set
membership.

**Image uploads.** Images are sharded into `media/posts/<year>/<month>/` with
UUID filenames, so a single directory never ends up holding millions of files
(a problem some filesystems handle very badly), and the original filename
(which might contain personal info) isn't preserved. Max size is capped at
5MB in the serializer.

## Scaling to millions of posts / reads

A few decisions in this codebase are specifically about the "assume millions
of posts and reads" requirement, beyond what's mentioned above:

- **Cursor pagination, not offset pagination.** `LIMIT/OFFSET` pagination
  gets slower the deeper you page, because the database still has to walk
  and discard every skipped row. Cursor pagination seeks directly on the
  indexed `(created_at, id)` tuple, so page 1 and page 10,000 cost the same.
- **Explicit composite indexes** on `(visibility, -created_at)` and
  `(author, -created_at)` for `Post`, and `(post, created_at)` /
  `(comment, created_at)` for `Comment`/`Reply` — these match the queries the
  feed and thread views actually run.
- **`select_related` everywhere an author is displayed**, so listing 10 posts
  costs 1 query for posts + 1 for "my likes" context, not 1 + N for authors.
- **Comments/replies are paginated, not fully inlined.** A post's detail
  response includes only a 2-comment preview (each with up to 3 replies);
  the full threads load via their own paginated endpoints
  (`/posts/{id}/comments/`, `/comments/{id}/replies/`) so a post with 50,000
  comments doesn't blow up the payload for everyone who scrolls past it.
- **`BigAutoField`** as the default PK type, since a normal `AutoField`
  (32-bit) can overflow well before "millions" turns into "billions," and
  there's no cost to using the bigger type from day one.

## Security notes

- Passwords are validated with Django's built-in validators (length,
  similarity-to-user-info, common-password, all-numeric checks) and hashed
  with PBKDF2 by default.
- JWT access tokens are short-lived; refresh tokens rotate and old ones are
  blacklisted, so a stolen refresh token has a limited window and can't be
  reused after rotation.
- Object-level permissions (`feed/permissions.py`) separate "can view/interact
  with this" (anyone, for public content) from "can edit/delete this" (author
  only) — so a like or comment doesn't accidentally require post ownership,
  while an edit or delete always does.
- `DEBUG` and `ALLOWED_HOSTS` are environment-driven; the settings file has
  commented-out `SECURE_*` flags to enable once deployed behind HTTPS.
- CORS is restricted to an explicit allow-list (`CORS_ALLOWED_ORIGINS`), not
  wildcarded.
- DRF throttling is enabled by default (300 req/min authenticated, 30/min
  anonymous) as a basic guard against abusive clients.

## What's intentionally out of scope

Per the brief: no "forgot password" flow, no follow/friend system, no feed
ranking/algorithm — the feed is strictly reverse-chronological across public
posts + the viewer's own private posts.

## Admin

`/admin/` is enabled with the custom `User` model registered, plus
`Post`/`Comment`/`Reply` with `raw_id_fields` for the FK pickers (which stays
fast even once the tables are large — a raw ID field doesn't try to render a
dropdown of a million rows).

## Suggested next steps for the frontend

- On login, store `access` in memory (e.g. a React context/hook) and attach
  it as `Authorization: Bearer <token>` on every request.
- On a 401, use the `refresh` token against `/api/auth/refresh/` to get a new
  `access` token before retrying the original request once.
- The feed screen should call `/api/posts/` with cursor pagination
  (`?cursor=...` from the `next` field) as the user scrolls.
