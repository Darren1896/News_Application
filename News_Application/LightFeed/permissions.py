from rest_framework import permissions


class IsJournalistForPost(permissions.BasePermission):
    """Only allows logged-in Journalists to submit new articles via POST"""

    def has_permission(self, request, view):
        if request.method == "POST":
            return (request.user.is_authenticated and
                    request.user.role == "journalist")
        return True


class IsAuthorOrEditorForWrite(permissions.BasePermission):
    """
    Journalists can only modify/delete their own articles.
    Editors can modify/delete any article (and approve).
    Readers have read-only access.
    """

    def has_object_permission(self, request, view, obj):
        # Read operations allowed for anyone authenticated
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated

        # Write operations restrictions
        if not request.user.is_authenticated:
            return False

        if request.user.role == "editor":
            return True  # Editors can change/delete anything

        if request.user.role == "journalist":
            # Journalists restricted to owned files
            return obj.author == request.user
        return False
