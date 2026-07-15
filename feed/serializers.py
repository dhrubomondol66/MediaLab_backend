from rest_framework import serializers
from django.contrib.auth import get_user_model
from users.serializers import UserPublicSerializer
from .models import Comment, CommentLike, Post, PostLike, Reply, ReplyLike
User = get_user_model()

MAX_IMAGE_SIZE_MB = 5

class ReplySerializer(serializers.ModelSerializer):
    author = UserPublicSerializer(read_only=True)
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Reply
        fields = ["id", "comment", "author", "text", "created_at", "likes_count", "is_liked"]
        read_only_fields = ["id", "comment", "author", "created_at", "likes_count"]

    def get_is_liked(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        liked_ids = self.context.get("liked_reply_ids")
        if liked_ids is not None:
            return obj.id in liked_ids
        return ReplyLike.objects.filter(reply=obj, user=request.user).exists()

    def validate_text(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Reply text cannot be empty.")
        return value


class CommentSerializer(serializers.ModelSerializer):
    author = UserPublicSerializer(read_only=True)
    is_liked = serializers.SerializerMethodField()
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id", "post", "author", "text", "created_at",
            "likes_count", "replies_count", "is_liked", "replies",
        ]
        read_only_fields = ["id", "post", "author", "created_at", "likes_count", "replies_count"]

    def get_is_liked(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        liked_ids = self.context.get("liked_comment_ids")
        if liked_ids is not None:
            return obj.id in liked_ids
        return CommentLike.objects.filter(comment=obj, user=request.user).exists()

    def get_replies(self, obj):
        # Only the top few replies are inlined; the full, paginated list is
        # available via GET /api/comments/{id}/replies/
        replies_qs = obj.replies.select_related("author").order_by("created_at", "id")[:3]
        return ReplySerializer(replies_qs, many=True, context=self.context).data

    def validate_text(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Comment text cannot be empty.")
        return value


class PostSerializer(serializers.ModelSerializer):
    author = UserPublicSerializer(read_only=True)
    likes_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    is_liked = serializers.SerializerMethodField()
    comments_preview = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id", "author", "text", "image", "visibility", "created_at", "updated_at",
            "likes_count", "comments_count", "is_liked", "comments_preview",
        ]
        read_only_fields = ["id", "author", "created_at", "updated_at"]

    def get_is_liked(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        liked_ids = self.context.get("liked_post_ids")
        if liked_ids is not None:
            return obj.id in liked_ids
        return PostLike.objects.filter(post=obj, user=request.user).exists()

    def get_comments_preview(self, obj):
        comments_qs = obj.comments.select_related("author").order_by("created_at", "id")[:2]
        return CommentSerializer(comments_qs, many=True, context=self.context).data

    def validate_image(self, value):
        if value and value.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
            raise serializers.ValidationError(f"Image must be smaller than {MAX_IMAGE_SIZE_MB}MB.")
        return value

    def validate(self, attrs):
        text = attrs.get("text", getattr(self.instance, "text", "") if self.instance else "")
        image = attrs.get("image", getattr(self.instance, "image", None) if self.instance else None)
        if not text and not image:
            raise serializers.ValidationError("A post needs either text or an image.")
        return attrs

    def create(self, validated_data):
        validated_data["author"] = self.context["request"].user
        return super().create(validated_data)


class LikeUserSerializer(serializers.Serializer):
    """Used by the 'who liked this' endpoints."""

    user = UserPublicSerializer(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)