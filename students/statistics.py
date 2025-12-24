from django.db.models import Sum, Max
from django.utils import timezone
from datetime import timedelta

from students.models import Attendance, Student, TestRecord, CompetitionScore, ExamRecord


class StudentStatisticsService:

    def __init__(self, student):
        self.student = student

    # 累積簽到
    def attendance_days(self):
        return Attendance.objects.filter(student=self.student).count()

    # 當週競技積分
    def weekly_competition_score(self):
        start = timezone.now().date() - timedelta(days=timezone.now().weekday())
        end = start + timedelta(days=7)
        return CompetitionScore.objects.filter(
            student=self.student,
            time__date__range=(start, end)
        ).aggregate(total=Sum("score"))["total"] or 0

    # 累積星數（每關卡取最高）
    def total_stars(self):
        records = TestRecord.objects.filter(
            student=self.student
        ).values(
            "island", "unit", "stage"
        ).annotate(
            max_stars=Max("stars")
        )
        return sum(r["max_stars"] for r in records)

    # 每島嶼星數
    def island_stars(self):
        records = TestRecord.objects.filter(
            student=self.student
        ).values(
            "island", "unit", "stage"
        ).annotate(
            max_stars=Max("stars")
        )
        result = {}
        for r in records:
            result.setdefault(r["island"], 0)
            result[r["island"]] += r["max_stars"]
        return result

    # 試卷成績
    def exam_scores(self):
        return ExamRecord.objects.filter(
            student=self.student
        ).values(
            "exam_paper__name",
            "score"
        )
    
    # =========================
    # 學校總計（給 union / global 用）
    # =========================
    @classmethod
    def get_school_total(cls, school_name):
        students = Student.objects.filter(school_name=school_name)
        return {
            "attendance_days": sum(cls(s).attendance_days() for s in students),
            "weekly_competition_score": sum(cls(s).weekly_competition_score() for s in students),
            "total_stars": sum(cls(s).total_stars() for s in students),
        }
