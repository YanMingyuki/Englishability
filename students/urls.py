# accounts/urls.py

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AttendanceAPIView,
    CompetitionScoreAPIView,
    DashboardClassAPIView,
    ExamHistoryAPIView,
    ForgotPasswordView,
    ImportExamPaperAPIView,
    LoginView,
    ExcelImportView,
    FirstChangePasswordView,
    MyStudentsView,
    ResetPasswordView,
    RetrieveExamPaperAPIView,
    StudentAchievementCreateAPIView,
    StudentAchievementListAPIView,
    StudentDetailDashboardAPIView,
    StudentTestSummaryAPIView,
    SubmitExamAPIView,
    WeeklyCompetitionRankingAPIView
)


urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("import-excel/", ExcelImportView.as_view(), name="import_excel"),
    path("forget-password/", ForgotPasswordView.as_view(), name="forget_password"),
    path("first-change-password/", FirstChangePasswordView.as_view(), name="first_change_password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    path("test-summary/",StudentTestSummaryAPIView.as_view(),name="student-test-summary"),
    path("my-students/", MyStudentsView.as_view(), name="my_students"),
    
    path("attendance/", AttendanceAPIView.as_view()),
    
    path("competition-score/", CompetitionScoreAPIView.as_view()),
    path("competition-score/weekly-ranking/", WeeklyCompetitionRankingAPIView.as_view()),
    
    path("exam-papers/import/", ImportExamPaperAPIView.as_view()),
    path("exam-papers/", RetrieveExamPaperAPIView.as_view()),
    path("exam-papers/submit/", SubmitExamAPIView.as_view()),
    path("exam-papers/history/", ExamHistoryAPIView.as_view()),


    path("dashboard/classes/",DashboardClassAPIView.as_view(),name="dashboard-classes"),
    path("dashboard/student/",StudentDetailDashboardAPIView.as_view(),name="dashboard-student-detail"),
    
    
        # POST 學生完成成就
    path("students/achievements/",StudentAchievementCreateAPIView.as_view(),name="student-achievement-create"),
    # GET 查詢學生已完成成就
    path("students/achievements/log/",StudentAchievementListAPIView.as_view(),name="student-achievement-list"),
]   
