# services/dashboard_service.py

from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import date

from students.models import Attendance, ExamRecord, Student, TestRecord



def today_range():
    today = date.today()
    return (
        timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time())),
        timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))
    )


def get_student_base_queryset():
    return Student.objects.all()


def get_today_attendance_count(student_qs):
    start, end = today_range()
    return Attendance.objects.filter(
        student__in=student_qs,
        time__range=(start, end)
    ).values("student").distinct().count()


def get_total_stars(student_qs):
    return TestRecord.objects.filter(
        student__in=student_qs
    ).aggregate(total=Sum("stars"))["total"] or 0


def get_today_points(student_qs):
    start, end = today_range()
    return TestRecord.objects.filter(
        student__in=student_qs,
        answer_time__range=(start, end)
    ).aggregate(total=Sum("score"))["total"] or 0


def get_exam_avg(student_qs):
    return ExamRecord.objects.filter(
        student__in=student_qs
    ).values("exam_paper__name").annotate(
        avg_score=Avg("score"),
        total=Count("id")
    )