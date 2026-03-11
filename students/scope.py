from students.models import Class, League, Student

class DataScopeService:
    """
    專門用於「統計資料」的身分可視範圍
    """

    def __init__(self, user):
        self.user = user
        self.role = user.role

    # =========================
    # teacher / school_admin
    # =========================
    def get_classes(self):
        if self.role == "teacher":
            teacher = self.user.teacher
            return Class.objects.filter(
                school_name=teacher.school_name,
                school_type=teacher.school_type,
                teachers__contains=[teacher.teacher_name]
            )

        if self.role == "school_admin":
            teacher = self.user.teacher
            return Class.objects.filter(
                school_name=teacher.school_name,
                school_type=teacher.school_type
            )

        return Class.objects.none()
    
    # =========================
    # union_leader：自己的聯盟
    # =========================
    def get_my_leagues(self):
        """
        union_leader：回傳自己聯盟內包含自己學校的所有 League
        """
        if self.role != "union_leader":
            return League.objects.none()

        teacher = getattr(self.user, "teacher", None)
        if not teacher:
            return League.objects.none()

        # 用 teacher 的 school_name 過濾
        return League.objects.filter(school_name=teacher.school_name)

    # =========================
    # global_leader 可視聯盟
    # =========================
    def get_all_leagues(self):
        return League.objects.all()
