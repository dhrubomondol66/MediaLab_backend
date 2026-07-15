from rest_framework.routers import DefaultRouter
from .views import CommentViewSet, PostViewSet, ReplyViewSet

router = DefaultRouter()
router.register("posts", PostViewSet, basename="post")
router.register("comments", CommentViewSet, basename="comment")
router.register("replies", ReplyViewSet, basename="reply")

urlpatterns = router.urls
