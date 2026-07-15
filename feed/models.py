import uuid
from datetime import date

from django.conf import settings
from django.db import models


def post_image_upload_path(instance, filename):
    """
    Shard uploads by year/month so a single directory never holds millions
    of files. UUID filename avoids collisions and leaking the original
    filename. Uses "today" rather than instance.created_at, since the model
    hasn't been saved yet at the point Django calls this callback.
    """
    ext = filename.split(".")[-1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"
    today = date.today()
    return f"posts/{today.year}/{today.month:02d}/{new_name}"


class Post(models.Model):
    PUBLIC = "public"
    PRIVATE = "private"
    VISIBILITY_CHOICES = [(PUBLIC, "Public"), (PRIVATE, "Private")]

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="posts", on_delete=models.CASCADE
    )
    text = models.TextField(blank=True)
    image = models.ImageField(upload_to=post_image_upload_path, blank=True, null=True)
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default=PUBLIC, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Denormalized counters avoid COUNT(*) over large related tables on every
    # feed render. Updated transactionally whenever a like/comment is added
    # or removed (see feed/services.py).
    likes_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["-created_at", "-id"], name="post_recent_idx"),
            models.Index(fields=["visibility", "-created_at"], name="post_visibility_idx"),
            models.Index(fields=["author", "-created_at"], name="post_author_idx"),
        ]

    def __str__(self):
        return f"Post({self.id}) by {self.author_id}"


class PostLike(models.Model):
    post = models.ForeignKey(Post, related_name="likes", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="post_likes", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "user"], name="unique_post_like")
        ]
        indexes = [models.Index(fields=["post", "user"])]


class Comment(models.Model):
    post = models.ForeignKey(Post, related_name="comments", on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="comments", on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    likes_count = models.PositiveIntegerField(default=0)
    replies_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["post", "created_at"], name="comment_post_idx")]

    def __str__(self):
        return f"Comment({self.id}) on Post({self.post_id})"


class CommentLike(models.Model):
    comment = models.ForeignKey(Comment, related_name="likes", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="comment_likes", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["comment", "user"], name="unique_comment_like")
        ]
        indexes = [models.Index(fields=["comment", "user"])]


class Reply(models.Model):
    comment = models.ForeignKey(Comment, related_name="replies", on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="replies", on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    likes_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["comment", "created_at"], name="reply_comment_idx")]

    def __str__(self):
        return f"Reply({self.id}) on Comment({self.comment_id})"


class ReplyLike(models.Model):
    reply = models.ForeignKey(Reply, related_name="likes", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="reply_likes", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["reply", "user"], name="unique_reply_like")
        ]
        indexes = [models.Index(fields=["reply", "user"])]
