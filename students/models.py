from django.db import models
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager
)

SCHOOL_TYPE_CHOICES = (
    ('國中', '國中'),
    ('國小', '國小'),
)
ROLE_CHOICES = [
    ('teacher', '老師'),
    ('school_admin', '學校管理員'),
    ('union_leader', '聯盟召集人'),
    ('global_leader', '總召集人'),
    ('student', '學生'),
]

# ============================
# User Manager
# ============================
class UserAccountManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('username 必填')

        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(username, password, **extra_fields)


# ============================
# Custom User
# ============================
class UserAccount(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=100, unique=True)  # 老師=email，學生=student_id
    email = models.EmailField(null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # 🔥 必要
    first_login = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserAccountManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []  # 🔥 一定要有

    def __str__(self):
        return self.username

class Teacher(models.Model):
    user = models.OneToOneField(UserAccount, on_delete=models.CASCADE)
    school_name = models.CharField(max_length=100)
    school_type = models.CharField(max_length=10)
    teacher_name = models.CharField(max_length=100)

    def __str__(self):
        return self.teacher_name

class Class(models.Model):
    school_name = models.CharField(max_length=100)
    school_type = models.CharField(max_length=10, choices=SCHOOL_TYPE_CHOICES)
    grade = models.IntegerField()
    classroom = models.CharField(max_length=20)

    # 使用 JSON 格式儲存多位老師名稱
    teachers = models.JSONField(default=list)  

    def __str__(self):
        return f"{self.school_name} {self.grade}-{self.classroom}"

class Student(models.Model):
    user = models.OneToOneField(UserAccount, on_delete=models.CASCADE)
    school_name = models.CharField(max_length=100)
    school_type = models.CharField(max_length=10)
    student_name = models.CharField(max_length=100)
    student_class = models.ForeignKey(Class, on_delete=models.CASCADE, related_name="students")
    student_id = models.CharField(max_length=50, unique=True)  # 🔥 帳號來源

    def __str__(self):
        return self.student_name

# 簽到記錄
class Attendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    time = models.DateTimeField()

    def __str__(self):
        return f"{self.student.student_name} @ {self.time}"

# 測驗紀錄
class TestRecord(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    answer_time = models.DateTimeField(default=timezone.now)  # 預設當下時間
    score = models.IntegerField()
    stars = models.IntegerField()
    stage = models.CharField(max_length=50)  # 關卡
    unit = models.CharField(max_length=50)
    island = models.CharField(max_length=50)
    correct_ratio = models.CharField(max_length=20)  # 新增欄位，格式如 "2/10"

    def __str__(self):
        return f"{self.student.student_name} 測驗紀錄"

# ======================
# 試卷
# ======================
class ExamPaper(models.Model):
    code = models.CharField(max_length=50, unique=True)   # ps-1
    name = models.CharField(max_length=100)
    level = models.CharField(max_length=20)               # 國小 / 國中
    info = models.CharField(max_length=50)                # 國小-1

    open_time = models.DateTimeField()
    close_time = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# ======================
# 試卷題型（EngToChi / ChiToEng / Listening）
# ======================
class ExamPart(models.Model):
    PART_CHOICES = (
        ("EngToChi", "英翻中"),
        ("ChiToEng", "中翻英"),
        ("Listening", "聽力"),
    )

    exam_paper = models.ForeignKey(
        ExamPaper, on_delete=models.CASCADE, related_name="parts"
    )
    part_key = models.CharField(max_length=20, choices=PART_CHOICES)

    def __str__(self):
        return f"{self.exam_paper.name} - {self.part_key}"


# ======================
# 試卷題目
# ======================
class ExamQuestion(models.Model):
    exam_part = models.ForeignKey(
        ExamPart, on_delete=models.CASCADE, related_name="questions"
    )

    external_id = models.IntegerField()  # JSON 題目 id
    question_type = models.CharField(max_length=50)

    question_text = models.TextField()
    answer = models.CharField(max_length=200)
    explanation = models.TextField(blank=True)

    island = models.CharField(max_length=50)
    unit = models.CharField(max_length=50)
    level = models.CharField(max_length=50)

    def __str__(self):
        return f"題目 {self.id}"


# ======================
# 試卷選項
# ======================
class ExamOption(models.Model):
    question = models.ForeignKey(
        ExamQuestion, on_delete=models.CASCADE, related_name="options"
    )
    external_id = models.IntegerField()
    description = models.CharField(max_length=200)

    def __str__(self):
        return self.description


# ======================
# 考試紀錄
# ======================
class ExamRecord(models.Model):
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE)
    exam_paper = models.ForeignKey(ExamPaper, on_delete=models.CASCADE)

    answer_time = models.DateTimeField(default=timezone.now)
    score = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.student.student_name} - {self.exam_paper.name}"
    
class ExamAnswerRecord(models.Model):
    exam_record = models.ForeignKey(
        "ExamRecord",
        on_delete=models.CASCADE,
        related_name="answers"
    )

    question = models.ForeignKey(
        "ExamQuestion",
        on_delete=models.CASCADE
    )

    selected_option = models.ForeignKey(
        ExamOption,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    selected_text = models.CharField(max_length=200, blank=True)

    correct_answer = models.CharField(max_length=200)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.exam_record.id} - Q{self.question.id}"
# ======================
# 聯盟
# ======================

class League(models.Model):
    league_name = models.CharField(max_length=100)
    school_type = models.CharField(max_length=10, choices=SCHOOL_TYPE_CHOICES)
    school_name = models.CharField(max_length=100)
    convener = models.CharField(max_length=100)
    def __str__(self):
        return self.league_name

# ======================
# 競技積分
# ======================
class CompetitionScore(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    score = models.IntegerField()
    time = models.DateTimeField()

    def __str__(self):
        return f"{self.student.student_name} 競技分數 {self.score}"


# ======================
# 成就
# ======================
class StudentAchievement(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="achievements"
    )
    # 只存成就名稱
    name = models.CharField(max_length=100)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "name")  # 保證同一學生不重複紀錄同一成就

    def __str__(self):
        return f"{self.student} - {self.name}"