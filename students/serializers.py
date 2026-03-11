# accounts/serializers.py

from rest_framework import serializers
from .models import ExamOption, ExamPaper, ExamQuestion, League, News, StudentAchievement, TestRecord, UserAccount, Teacher, Student, Class
from django.db.models import Sum


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class ExcelUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class FirstChangePasswordSerializer(serializers.Serializer):
    skip_change = serializers.BooleanField(required=False, default=False)
    new_password = serializers.CharField(
        min_length=6,
        required=False,
        allow_blank=True
    )

    def validate(self, attrs):
        skip_change = attrs.get("skip_change", False)
        new_password = attrs.get("new_password")

        if not skip_change and not new_password:
            raise serializers.ValidationError(
                "請提供新密碼或選擇跳過"
            )

        return attrs


class StudentOutputSerializer(serializers.ModelSerializer):
    grade = serializers.IntegerField(source="student_class.grade")
    classroom = serializers.CharField(source="student_class.classroom")

    class Meta:
        model = Student
        fields = ["student_name", "student_id", "grade", "classroom"]

class ForgotPasswordSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    
class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=6)
    
class TestRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestRecord
        fields = ['id', 'student', 'answer_time', 'score', 'stars', 'stage', 'unit', 'island', 'correct_ratio']
        read_only_fields = ['student', 'answer_time', 'score', 'stars', 'correct_ratio']
        
class ExamOptionImportSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()

class ExamQuestionImportSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    island = serializers.CharField()
    unit = serializers.CharField()
    level = serializers.CharField()
    type = serializers.CharField()
    question_text = serializers.CharField()
    answer = serializers.CharField()
    explanation = serializers.CharField(allow_blank=True)
    options = ExamOptionImportSerializer(many=True)

class ExamPaperImportSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    level = serializers.CharField()
    info = serializers.CharField()
    parts = serializers.DictField(
        child=ExamQuestionImportSerializer(many=True)
    )
    
#取得考試卷
class ExamOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamOption
        fields = ("id", "external_id", "description")


class ExamQuestionSerializer(serializers.ModelSerializer):
    options = ExamOptionSerializer(many=True)

    class Meta:
        model = ExamQuestion
        fields = (
            "id",           # 🔥 系統唯一
            "external_id",
            "island",
            "unit",
            "level",
            "question_type",
            "question_text",
            "options",
        )
class ExamPaperRetrieveSerializer(serializers.ModelSerializer):
    parts = serializers.SerializerMethodField()

    class Meta:
        model = ExamPaper
        fields = (
            "code",
            "name",
            "level",
            "info",
            "open_time",
            "close_time",
            "parts",
        )

    def get_parts(self, obj):
        result = {}
        for part in obj.parts.all():
            result[part.part_key] = ExamQuestionSerializer(
                part.questions.all(), many=True
            ).data
        return result  

# 考試卷計分並記錄
class AnswerSubmitSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()          # 🔥 ExamQuestion.id
    selected_option_id = serializers.IntegerField(
        required=False,
        allow_null=True
    )

class ExamSubmitSerializer(serializers.Serializer):
    code = serializers.CharField()
    answers = AnswerSubmitSerializer(many=True)

# 查詢考試紀錄
class AnswerOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamOption
        fields = ("id", "description")


class ExamHistoryQuestionSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    question_text = serializers.CharField()
    options = AnswerOptionSerializer(many=True)

    selected_option_id = serializers.IntegerField(allow_null=True)
    selected_text = serializers.CharField()
    correct_answer = serializers.CharField()
    is_correct = serializers.BooleanField()
    
class StudentDashboardSerializer(serializers.Serializer):
    student_id = serializers.CharField()
    student_name = serializers.CharField()
    attendance_days = serializers.IntegerField()
    weekly_competition_score = serializers.IntegerField()
    total_stars = serializers.IntegerField()


class ClassDashboardSerializer(serializers.Serializer):
    class_id = serializers.IntegerField(required=False)
    class_name = serializers.CharField(required=False)
    students = StudentDashboardSerializer(many=True, required=False)
    total_attendance_days = serializers.IntegerField(required=False)
    total_weekly_score = serializers.IntegerField(required=False)
    total_stars = serializers.IntegerField(required=False)
    school_name = serializers.CharField(required=False)

    
class StudentAchievementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentAchievement
        fields = ["name"]   
    
class StudentAchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentAchievement
        fields = ["name", "completed_at"]    
    
class StudentDetailSerializer(serializers.ModelSerializer):
    total_stars = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "id",
            "student_name",
            "student_id",
            "total_stars"
        ]

    def get_total_stars(self, obj):
        return TestRecord.objects.filter(
            student=obj
        ).aggregate(total=Sum("stars"))["total"] or 0
        
class ClassDetailSerializer(serializers.ModelSerializer):
    students = StudentDetailSerializer(many=True, read_only=True)
    student_total = serializers.SerializerMethodField()

    class Meta:
        model = Class
        fields = [
            "id",
            "grade",
            "classroom",
            "student_total",
            "students"
        ]

    def get_student_total(self, obj):
        return obj.students.count()

class SchoolSummarySerializer(serializers.Serializer):
    class_total = serializers.IntegerField()
    student_total = serializers.IntegerField()
    today_participation = serializers.IntegerField()
    today_total_points = serializers.IntegerField()
    total_stars = serializers.IntegerField()
    
class ClassListSerializer(serializers.ModelSerializer):
    student_total = serializers.IntegerField()
    total_stars = serializers.IntegerField()

    class Meta:
        model = Class
        fields = [
            "id",
            "grade",
            "classroom",
            "student_total",
            "total_stars"
        ]

class SchoolListSerializer(serializers.Serializer):
    school_name = serializers.CharField()
    student_total = serializers.IntegerField()
    total_stars = serializers.IntegerField()
    
class LeagueListSerializer(serializers.ModelSerializer):
    school_total = serializers.IntegerField()
    student_total = serializers.IntegerField()
    total_stars = serializers.IntegerField()

    class Meta:
        model = League
        fields = [
            "id",
            "league_name",
            "school_total",
            "student_total",
            "total_stars"
        ]
        
class StudentSimpleSerializer(serializers.ModelSerializer):
    total_stars = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "id",
            "student_name",
            "student_id",
            "total_stars"
        ]

    def get_total_stars(self, obj):
        return TestRecord.objects.filter(
            student=obj
        ).aggregate(total=Sum("stars"))["total"] or 0

class ExamStatsSerializer(serializers.Serializer):
    exam_id = serializers.IntegerField()
    exam_name = serializers.CharField()
    total_participants = serializers.IntegerField()
    avg_score = serializers.FloatField()
    highest_score = serializers.IntegerField()
    lowest_score = serializers.IntegerField()

class NewsSerializer(serializers.ModelSerializer):
    class Meta:
        model = News
        fields = '__all__'

