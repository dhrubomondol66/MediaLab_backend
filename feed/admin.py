from django.contrib import admin

from .models import Comment, CommentLike, Post, PostLike, Reply, ReplyLike


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["id", "author", "visibility", "likes_count", "comments_count", "created_at"]
    list_filter = ["visibility", "created_at"]
    search_fields = ["text", "author__email"]
    raw_id_fields = ["author"]
    
    def likes_count(self, obj):
        return obj.postlike_set.count()
    likes_count.short_description = "Likes"


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["id", "post", "author", "likes_count", "replies_count", "created_at"]
    raw_id_fields = ["post", "author"]

    def likes_count(self, obj):
        return obj.commentlike_set.count()
    likes_count.short_description = "Likes"

    def replies_count(self, obj):
        return obj.reply_set.count()
    replies_count.short_description = "Replies"


@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ["id", "comment", "author", "likes_count", "created_at"]
    raw_id_fields = ["comment", "author"]

    def likes_count(self, obj):
        return obj.replylike_set.count()
    likes_count.short_description = "Likes"


admin.site.register(PostLike)
admin.site.register(CommentLike)
admin.site.register(ReplyLike)
