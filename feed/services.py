from django.db import IntegrityError, transaction
from django.db.models import F

from .models import Comment, CommentLike, Post, PostLike, Reply, ReplyLike


def toggle_post_like(post: Post, user) -> bool:
    """Returns True if the post is now liked, False if it was just unliked."""
    with transaction.atomic():
        deleted, _ = PostLike.objects.filter(post=post, user=user).delete()
        if deleted:
            Post.objects.filter(pk=post.pk).update(likes_count=F("likes_count") - 1)
            return False
        try:
            PostLike.objects.create(post=post, user=user)
        except IntegrityError:
            # Race: another concurrent request created it first; treat as already-liked.
            return True
        Post.objects.filter(pk=post.pk).update(likes_count=F("likes_count") + 1)
        return True


def toggle_comment_like(comment: Comment, user) -> bool:
    with transaction.atomic():
        deleted, _ = CommentLike.objects.filter(comment=comment, user=user).delete()
        if deleted:
            Comment.objects.filter(pk=comment.pk).update(likes_count=F("likes_count") - 1)
            return False
        try:
            CommentLike.objects.create(comment=comment, user=user)
        except IntegrityError:
            return True
        Comment.objects.filter(pk=comment.pk).update(likes_count=F("likes_count") + 1)
        return True


def toggle_reply_like(reply: Reply, user) -> bool:
    with transaction.atomic():
        deleted, _ = ReplyLike.objects.filter(reply=reply, user=user).delete()
        if deleted:
            Reply.objects.filter(pk=reply.pk).update(likes_count=F("likes_count") - 1)
            return False
        try:
            ReplyLike.objects.create(reply=reply, user=user)
        except IntegrityError:
            return True
        Reply.objects.filter(pk=reply.pk).update(likes_count=F("likes_count") + 1)
        return True


def create_comment(post: Post, author, text: str) -> Comment:
    with transaction.atomic():
        comment = Comment.objects.create(post=post, author=author, text=text)
        Post.objects.filter(pk=post.pk).update(comments_count=F("comments_count") + 1)
    return comment


def delete_comment(comment: Comment):
    with transaction.atomic():
        post_id = comment.post_id
        comment.delete()
        Post.objects.filter(pk=post_id).update(comments_count=F("comments_count") - 1)


def create_reply(comment: Comment, author, text: str) -> Reply:
    with transaction.atomic():
        reply = Reply.objects.create(comment=comment, author=author, text=text)
        Comment.objects.filter(pk=comment.pk).update(replies_count=F("replies_count") + 1)
    return reply


def delete_reply(reply: Reply):
    with transaction.atomic():
        comment_id = reply.comment_id
        reply.delete()
        Comment.objects.filter(pk=comment_id).update(replies_count=F("replies_count") - 1)
