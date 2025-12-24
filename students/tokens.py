from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import BasePermission

class CustomRefreshToken(RefreshToken):

    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)

        # 共用
        token["role"] = user.role
        token["user_id"] = user.id

        # 🔥 學生
        if user.role == "student" and hasattr(user, "student"):
            token["student_id"] = user.student.id

        # 🔥 老師
        if user.role != "student" and hasattr(user, "teacher"):
            token["teacher_id"] = user.teacher.id

        return token

class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'student'
            and hasattr(request.user, 'student')
        )