from rest_framework import permissions

OWNER_ONLY_ACTIONS = {"update", "partial_update", "destroy"}

def owner_id_natches(owner, user):
    return owner is not None and user is not None and owner.pk == user.pk


class IsOwnerOrReadOnlyPublic(permissions.BasePermission):
    """
    - A PUBLIC post is visible to, and can be liked/commented on by, any
      authenticated user.
    - A PRIVATE post is visible only to its author.
    - Editing or deleting a post is always author-only.
    """
    def has_object_permission(self, request, view, obj):
        owner = getattr(obj, "author", None)
        visibility = getattr(obj, "visibility", "public")
        action = getattr(view, "action", None)

        if action in OWNER_ONLY_ACTIONS:
            return owner_id_matches(owner, request.user)

        if visibility == "private":
            return owner_id_matches(owner, request.user)
        return True

class IsAuthorOrReadOnly(permissions.BasePermission):
    """
    For comments/replies: any authenticated user can read, like, or reply.
    Editing or deleting a comment/reply is author-only.
    """
    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)
        if action in OWNER_ONLY_ACTIONS:
            return owner_id_matches(obj.author, request.user)
        return True