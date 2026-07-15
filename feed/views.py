from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Comment, CommentLike, Post, PostLike, Reply, ReplyLike
from .pagination import FeedCursorPagination, RepliesCursorPagination
from .permissions import IsAuthorOrReadOnly, IsOwnerOrReadOnlyPublic
from .serializers import CommentSerializer, LikeUserSerializer, PostSerializer, ReplySerializer
from .services import (
    create_comment, create_reply, delete_comment, delete_reply,
    toggle_comment_like, toggle_post_like, toggle_reply_like,
)


class PostViewSet(viewsets.ModelViewSet):
    """
    /posts/                 GET (feed, newest first) / POST (create)
    /posts/{id}/            GET / PATCH / DELETE  (author only for write)
    /posts/{id}/like/       POST  (toggle like/unlike)
    /posts/{id}/likes/      GET   (who liked this post)
    /posts/{id}/comments/   GET   (paginated comments) / POST (add comment)
    """

    serializer_class = PostSerializer
    pagination_class = FeedCursorPagination
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnlyPublic]

    def get_queryset(self):
        user = self.request.user
        """
        - Feed rule: everyone sees public posts; private posts are visible
        - only to their author. select_related avoids an author query per row;
        - counters are denormalized so no aggregate COUNT queries are needed.
        """
        qs = (
            Post.objects.select_related("author")
            .filter(Q(visibility=Post.PUBLIC) | Q(visibility=Post.PRIVATE, author=user))
        )

        author_id = self.request.query_params.get("author")
        if author_id:
            qs = qs.filter(author_id=author_id)

        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            """
            Bulk-fetch "did I like this" state for the current page instead
            of running one EXISTS query per post/comment/reply (N+1 avoidance).
            """
            context["liked_post_ids"] = set(
                PostLike.objects.filter(user=user).values_list("post_id", flat=True)
            )
            context["liked_comment_ids"] = set(
                CommentLike.objects.filter(user=user).values_list("comment_id", flat=True)
            )
            context["liked_reply_ids"] = set(
                ReplyLike.objects.filter(user=user).values_list("reply_id", flat=True)
            )
        return context

    def perform_destroy(self, instance):
        instance.delete()

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        post = self.get_object()
        is_liked = toggle_post_like(post, request.user)
        post.refresh_from_db(fields=["likes_count"])
        return Response({"is_liked": is_liked, "likes_count": post.likes_count})

    @action(detail=True, methods=["get"])
    def likes(self, request, pk=None):
        post = self.get_object()
        likes_qs = PostLike.objects.filter(post=post).select_related("user").order_by("-created_at")
        page = self.paginate_queryset(likes_qs)
        data = LikeUserSerializer(page, many=True).data
        return self.get_paginated_response(data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        post = self.get_object()
        if request.method == "POST":
            serializer = CommentSerializer(data=request.data, context=self.get_serializer_context())
            serializer.is_valid(raise_exception=True)
            comment = create_comment(post, request.user, serializer.validated_data["text"])
            out = CommentSerializer(comment, context=self.get_serializer_context())
            return Response(out.data, status=status.HTTP_201_CREATED)

        comments_qs = post.comments.select_related("author").order_by("created_at", "id")
        page = self.paginate_queryset(comments_qs)
        data = CommentSerializer(page, many=True, context=self.get_serializer_context()).data
        return self.get_paginated_response(data)


class CommentViewSet(viewsets.GenericViewSet):
    """
    /comments/{id}/            DELETE (author only)
    /comments/{id}/like/       POST   (toggle like/unlike)
    /comments/{id}/likes/      GET    (who liked this comment)
    /comments/{id}/replies/    GET    (paginated replies) / POST (add reply)
    """

    queryset = Comment.objects.select_related("author", "post")
    serializer_class = CommentSerializer
    pagination_class = RepliesCursorPagination
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            context["liked_comment_ids"] = set(
                CommentLike.objects.filter(user=user).values_list("comment_id", flat=True)
            )
            context["liked_reply_ids"] = set(
                ReplyLike.objects.filter(user=user).values_list("reply_id", flat=True)
            )
        return context

    def destroy(self, request, pk=None):
        comment = self.get_object()
        self.check_object_permissions(request, comment)
        delete_comment(comment)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        comment = self.get_object()
        is_liked = toggle_comment_like(comment, request.user)
        comment.refresh_from_db(fields=["likes_count"])
        return Response({"is_liked": is_liked, "likes_count": comment.likes_count})

    @action(detail=True, methods=["get"])
    def likes(self, request, pk=None):
        comment = self.get_object()
        likes_qs = CommentLike.objects.filter(comment=comment).select_related("user").order_by("-created_at")
        page = self.paginate_queryset(likes_qs)
        data = LikeUserSerializer(page, many=True).data
        return self.get_paginated_response(data)

    @action(detail=True, methods=["get", "post"])
    def replies(self, request, pk=None):
        comment = self.get_object()
        if request.method == "POST":
            serializer = ReplySerializer(data=request.data, context=self.get_serializer_context())
            serializer.is_valid(raise_exception=True)
            reply = create_reply(comment, request.user, serializer.validated_data["text"])
            out = ReplySerializer(reply, context=self.get_serializer_context())
            return Response(out.data, status=status.HTTP_201_CREATED)

        replies_qs = comment.replies.select_related("author").order_by("created_at", "id")
        page = self.paginate_queryset(replies_qs)
        data = ReplySerializer(page, many=True, context=self.get_serializer_context()).data
        return self.get_paginated_response(data)


class ReplyViewSet(viewsets.GenericViewSet):
    """
    /replies/{id}/          DELETE (author only)
    /replies/{id}/like/     POST   (toggle like/unlike)
    /replies/{id}/likes/    GET    (who liked this reply)
    """

    queryset = Reply.objects.select_related("author", "comment")
    serializer_class = ReplySerializer
    pagination_class = FeedCursorPagination
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]

    def destroy(self, request, pk=None):
        reply = self.get_object()
        self.check_object_permissions(request, reply)
        delete_reply(reply)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def like(self, request, pk=None):
        reply = self.get_object()
        is_liked = toggle_reply_like(reply, request.user)
        reply.refresh_from_db(fields=["likes_count"])
        return Response({"is_liked": is_liked, "likes_count": reply.likes_count})

    @action(detail=True, methods=["get"])
    def likes(self, request, pk=None):
        reply = self.get_object()
        likes_qs = ReplyLike.objects.filter(reply=reply).select_related("user").order_by("-created_at")
        page = self.paginate_queryset(likes_qs)
        data = LikeUserSerializer(page, many=True).data
        return self.get_paginated_response(data)
