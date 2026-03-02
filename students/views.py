import logging
from collections import defaultdict
from datetime import datetime
import pandas as pd
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import make_aware

from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import (RefreshToken,UntypedToken,TokenError,BlacklistedToken,OutstandingToken,)

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from .tasks import send_reset_password_email

from .tokens import CustomRefreshToken, IsStudent

from students.scope import DataScopeService
from students.statistics import StudentStatisticsService

from .models import (Attendance,Class,CompetitionScore,ExamAnswerRecord, ExamOption,ExamPaper,ExamPart,ExamQuestion,ExamRecord,League,Student, StudentAchievement,Teacher, TestRecord, UserAccount,)

from .serializers import (ClassDashboardSerializer, ExamPaperImportSerializer,ExamPaperRetrieveSerializer,ExamSubmitSerializer,FirstChangePasswordSerializer,ForgotPasswordSerializer,LoginSerializer, ResetPasswordSerializer, StudentAchievementCreateSerializer, StudentAchievementSerializer,StudentOutputSerializer,)

logger = logging.getLogger(__name__)
DEFAULT_PASSWORD = "ENpassword123"  # 統一預設密碼


# --------------------------------
# Login API
# --------------------------------
class LoginView(APIView):
    permission_classes = []

    @swagger_auto_schema(
        operation_description="登入系統 (老師使用 email；學生使用 student_id)",
        operation_summary="登入",
        request_body=LoginSerializer,
        responses={200: "登入成功"}
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        login_input = serializer.validated_data["username"]
        password = serializer.validated_data["password"]

        user = UserAccount.objects.filter(username=login_input).first()
        if not user:
            user = UserAccount.objects.filter(email=login_input).first()
        if not user:
            return Response({"detail": "帳號不存在"}, status=400)

        if not check_password(password, user.password):
            return Response({"detail": "密碼錯誤"}, status=400)

        refresh = CustomRefreshToken.for_user(user)

        response_data = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "role": user.role,
            "first_login": user.first_login,
        }

        # ✅ 如果是學生，加上 student_id
        if user.role == "student":
            student = getattr(user, "student", None)
            response_data["student_id"] = student.id if student else None

        return Response(response_data)
# --------------------------------
# Excel Import API
# --------------------------------
class ExcelImportView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = []

    @swagger_auto_schema(
        operation_description="匯入 Excel，自動建立老師、學生與班級資料",
        manual_parameters=[
            openapi.Parameter(
                name="file",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                description="上傳 Excel 檔案（.xlsx）",
                required=True,
            )
        ],
        responses={
            200: openapi.Response(
                description="匯入成功",
                examples={"application/json": {"detail": "Excel 匯入成功"}}
            )
        }
    )
    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "請提供 Excel 檔案"}, status=400)

        # ================================
        # 1️⃣ 讀取 Excel
        # ================================
        df = pd.read_excel(file, dtype={"student_id": str})
        df.columns = df.columns.str.strip().str.lower()

        column_map = {
            "姓名": "name",
            "名字": "name",
        }
        df.rename(columns=column_map, inplace=True)

        logger.warning("=== Excel 欄位 ===")
        logger.warning(df.columns.tolist())
        logger.warning("=== Excel 資料 ===")
        logger.warning("\n" + df.to_string())

        # ================================
        # 2️⃣ 必要欄位檢查
        # ================================
        required_cols = ["role", "school_name", "school_type", "name"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            return Response(
                {
                    "detail": "Excel 缺少必要欄位",
                    "missing_columns": missing,
                },
                status=400,
            )

        # ================================
        # 3️⃣ 交易處理（非常重要）
        # ================================
        with transaction.atomic():

            for index, row in df.iterrows():
                role = str(row["role"]).strip().lower()
                school_name = str(row["school_name"]).strip()
                school_type = str(row["school_type"]).strip()
                name = str(row["name"]).strip()

                # ============================
                # 👩‍🏫 老師
                # ============================
                if role != "student":
                    email = str(row.get("email", "")).strip()
                    grade = int(row["grade"])
                    classroom = str(row["classroom"]).strip()

                    user, _ = UserAccount.objects.get_or_create(
                        username=email,
                        defaults={
                            "email": email,
                            "role": role,
                        }
                    )
                    user.set_password(DEFAULT_PASSWORD)
                    user.save()

                    teacher, _ = Teacher.objects.get_or_create(
                        user=user,
                        defaults={
                            "school_name": school_name,
                            "school_type": school_type,
                            "teacher_name": name,
                        }
                    )

                    cls, _ = Class.objects.get_or_create(
                        school_name=school_name,
                        school_type=school_type,
                        grade=grade,
                        classroom=classroom,
                        defaults={"teachers": []}
                    )

                    # ⭐ 關鍵修正：同步寫入老師
                    if name not in cls.teachers:
                        cls.teachers.append(name)
                        cls.save()

                # ============================
                # 👨‍🎓 學生
                # ============================
                else:
                    raw_sid = str(row.get("student_id", "")).strip()
                    if raw_sid.lower() == "nan" or not raw_sid:
                        raise ValueError(f"第 {index+2} 列學生缺少 student_id")

                    if raw_sid.endswith(".0"):
                        raw_sid = raw_sid[:-2]
                    student_id = raw_sid

                    grade = int(row["grade"])
                    classroom = str(row["classroom"]).strip()

                    user, _ = UserAccount.objects.get_or_create(
                        username=student_id,
                        defaults={"role": "student"}
                    )
                    user.set_password(DEFAULT_PASSWORD)
                    user.save()

                    cls, _ = Class.objects.get_or_create(
                        school_name=school_name,
                        school_type=school_type,
                        grade=grade,
                        classroom=classroom,
                        defaults={"teachers": []}
                    )

                    Student.objects.get_or_create(
                        user=user,
                        defaults={
                            "school_name": school_name,
                            "school_type": school_type,
                            "student_name": name,
                            "student_class": cls,
                            "student_id": student_id,
                        }
                    )

        return Response({"detail": "Excel 匯入成功"})

# --------------------------------
# First Login: Change password
# --------------------------------
class FirstChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="首次登入修改密碼",
        operation_description="首次登入可選擇是否修改密碼",
        request_body=FirstChangePasswordSerializer,
        responses={200: "密碼已更新（first_login 改為 false）"}
    )
    def post(self, request):
        serializer = FirstChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        skip_change = serializer.validated_data.get("skip_change")
        new_password = serializer.validated_data.get("new_password")

        if skip_change:
            user.first_login = False
        else:
            user.set_password(new_password)
            user.first_login = False

        user.save()
        return Response({"detail": "首次登入完成"})


# --------------------------------
# Teacher Query Students
# --------------------------------
class MyStudentsView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="英文老師查詢自己所教班級的所有學生",
        responses={
            200: StudentOutputSerializer(many=True),
            403: "沒有權限"
        }
    )
    def get(self, request):
        user = request.user

        if user.role != "english":
            return Response({"detail": "沒有權限"}, status=403)

        teacher = user.teacher
        classes = Class.objects.filter(teachers__contains=[teacher.teacher_name])
        students = Student.objects.filter(student_class__in=classes)

        serializer = StudentOutputSerializer(students, many=True)
        return Response(serializer.data)


class ForgotPasswordView(APIView):
    permission_classes = []

    @swagger_auto_schema(
        operation_summary="忘記密碼",
        operation_description="忘記密碼功能（寄送重設密碼連結至指定 Email）",
        request_body=ForgotPasswordSerializer,
        responses={200: "已寄送重設密碼信件"}
    )
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data["username"]
        email = serializer.validated_data["email"]

        try:
            user = UserAccount.objects.get(username=username)
        except UserAccount.DoesNotExist:
            return Response({"detail": "帳號不存在"}, status=400)

        if user.role != "student":
            return Response({"detail": "僅學生可用此功能"}, status=400)

        student = user.student

        # 建立 reset token
        reset_token = RefreshToken.for_user(user).access_token
        reset_url = settings.FRONTEND_URL + f"/login/{reset_token}/"

        # Celery 背景寄送（只寄給前端輸入的 email）
        send_reset_password_email.delay(
            [email],                     # 收件者
            student.student_name,
            student.student_id,
            reset_url
        )

        return Response({"detail": "密碼重設連結已寄送"})
    
class ResetPasswordView(APIView):
    permission_classes = [] 
    @swagger_auto_schema(
        operation_summary="重設密碼",
        operation_description="學生重設密碼（授課老師寄來的重設連結）",
        request_body=ResetPasswordSerializer,
        responses={200: "密碼重設成功"}
    )
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        # 1️⃣ 驗證 token 是否有效
        try:
            validated_token = UntypedToken(token)
        except TokenError:
            return Response({"detail": "重設密碼連結無效或已失效"}, status=400)

        # 2️⃣ 從 token 取 user_id
        user_id = validated_token["user_id"]

        try:
            user = UserAccount.objects.get(id=user_id)
        except UserAccount.DoesNotExist:
            return Response({"detail": "使用者不存在"}, status=400)

        # 3️⃣ 設定新密碼（正確方式）
        user.set_password(new_password)
        user.save()

        # 4️⃣ 將 token 作廢（加入 blacklist）
        try:
            token_obj = OutstandingToken.objects.get(token=token)
            BlacklistedToken.objects.create(token=token_obj)
        except:
            pass  # 若找不到代表 token 用過，跳過即可

        return Response({"detail": "密碼重設成功"}, status=200)
    
class StudentTestSummaryAPIView(APIView):
    """
    查詢學生自己的測驗成績（以關卡為基底，取最高答對率/星數）
    """
    permission_classes = [IsAuthenticated, IsStudent]

    @swagger_auto_schema(
        operation_summary="查詢學生測驗成績總覽",
        operation_description="""
        - 以「關卡(stage)」為基底
        - 同一關卡只取最高星數（若相同則比答對題數）
        - 回傳巢狀結構：島嶼 → 單元 → 關卡
        """,
        responses={
            200: openapi.Response(
                description="學生測驗成績總覽",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "student_id": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="學生 ID"
                        ),
                        "total_stars": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            description="學生累積總星數（每關卡取最高）"
                        ),
                        "islands": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "island_name": openapi.Schema(
                                        type=openapi.TYPE_STRING,
                                        description="島嶼名稱"
                                    ),
                                    "total_stars": openapi.Schema(
                                        type=openapi.TYPE_INTEGER,
                                        description="該島嶼總星數"
                                    ),
                                    "units": openapi.Schema(
                                        type=openapi.TYPE_ARRAY,
                                        items=openapi.Schema(
                                            type=openapi.TYPE_OBJECT,
                                            properties={
                                                "unit_name": openapi.Schema(
                                                    type=openapi.TYPE_STRING,
                                                    description="單元名稱"
                                                ),
                                                "total_stars": openapi.Schema(
                                                    type=openapi.TYPE_INTEGER,
                                                    description="該單元總星數"
                                                ),
                                                "stages": openapi.Schema(
                                                    type=openapi.TYPE_ARRAY,
                                                    items=openapi.Schema(
                                                        type=openapi.TYPE_OBJECT,
                                                        properties={
                                                            "stage": openapi.Schema(
                                                                type=openapi.TYPE_STRING,
                                                                description="關卡名稱"
                                                            ),
                                                            "stars": openapi.Schema(
                                                                type=openapi.TYPE_INTEGER,
                                                                description="此關卡獲得星數（最高）"
                                                            ),
                                                            "correct_ratio": openapi.Schema(
                                                                type=openapi.TYPE_STRING,
                                                                description="答對率，如 8/10"
                                                            )
                                                        }
                                                    )
                                                )
                                            }
                                        )
                                    )
                                }
                            )
                        )
                    }
                )
            ),
            403: "無學生身分",
        },
    )
    def get(self, request):
        user = request.user
        student = getattr(user, 'student', None)

        if not student:
            return Response({"error": "無法取得學生資訊"}, status=403)

        records = TestRecord.objects.filter(student=student)

        best_stage_record = {}

        for r in records:
            key = (r.island, r.unit, r.stage)

            if key not in best_stage_record:
                best_stage_record[key] = r
            else:
                if r.stars > best_stage_record[key].stars:
                    best_stage_record[key] = r
                elif r.stars == best_stage_record[key].stars and r.score > best_stage_record[key].score:
                    best_stage_record[key] = r

        data = {
            "student_id": student.id,
            "total_stars": 0,
            "islands": []
        }

        island_map = defaultdict(lambda: {
            "total_stars": 0,
            "units": defaultdict(lambda: {
                "total_stars": 0,
                "stages": []
            })
        })

        for (island, unit, stage), record in best_stage_record.items():
            island_map[island]["total_stars"] += record.stars
            island_map[island]["units"][unit]["total_stars"] += record.stars

            island_map[island]["units"][unit]["stages"].append({
                "stage": stage,
                "stars": record.stars,
                "correct_ratio": record.correct_ratio
            })

            data["total_stars"] += record.stars

        for island_name, island_data in island_map.items():
            units_list = []

            for unit_name, unit_data in island_data["units"].items():
                units_list.append({
                    "unit_name": unit_name,
                    "total_stars": unit_data["total_stars"],
                    "stages": unit_data["stages"]
                })

            data["islands"].append({
                "island_name": island_name,
                "total_stars": island_data["total_stars"],
                "units": units_list
            })

        return Response(data)
   
# 簽到 
class AttendanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="學生簽到",
        responses={
            200: openapi.Response(
                description="簽到成功",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(type=openapi.TYPE_STRING)
                    }
                )
            ),
            400: openapi.Response(description="今日已簽到"),
            403: openapi.Response(description="無學生身分")
        },
        tags=["attendance"]
    )
    def post(self, request):
        student = getattr(request.user, "student", None)
        if not student:
            return Response({"message": "無學生身分"}, status=403)

        today = timezone.localdate()

        if Attendance.objects.filter(
            student=student,
            time__date=today
        ).exists():
            return Response({"message": "今日已簽到"}, status=400)

        Attendance.objects.create(
            student=student,
            time=timezone.now()
        )

        return Response({"message": "簽到成功"})

    @swagger_auto_schema(
        operation_summary="查詢簽到狀態或紀錄",
        manual_parameters=[
            openapi.Parameter(
                "type",
                openapi.IN_QUERY,
                description="today：查詢今日是否簽到 / history：查詢學生簽到紀錄",
                type=openapi.TYPE_STRING,
                required=True,
                enum=["today", "history"]
            ),
            openapi.Parameter(
                "student_id",
                openapi.IN_QUERY,
                description="學生 ID（type=history 時必填）",
                type=openapi.TYPE_INTEGER,
                required=False
            ),
        ],
        responses={
            200: openapi.Response(
                description="查詢成功"
            ),
            400: openapi.Response(description="參數錯誤"),
            403: openapi.Response(description="權限不足")
        },
        tags=["attendance"]
    )
    def get(self, request):
        query_type = request.query_params.get("type")

        if query_type == "today":
            student = getattr(request.user, "student", None)
            if not student:
                return Response({"checked_in": False})

            today = timezone.localdate()

            record = Attendance.objects.filter(
                student=student,
                time__date=today
            ).order_by("time").first()

            if not record:
                return Response({
                    "checked_in": False,
                    "time": None
                })

            return Response({
                "checked_in": True,
                "time": record.time
            })

        elif query_type == "history":
            student_id = request.query_params.get("student_id")
            if not student_id:
                return Response({"error": "student_id 必填"}, status=400)

            try:
                student = Student.objects.get(id=student_id)
            except Student.DoesNotExist:
                return Response({"error": "學生不存在"}, status=404)

            records = Attendance.objects.filter(student=student).order_by("-time")

            return Response({
                "student_id": student.id,
                "records": [{"time": r.time} for r in records]
            })

        return Response({"error": "type 參數錯誤"}, status=400)
# 競技積分
class CompetitionScoreAPIView(APIView):
    """
    競技積分 API
    - POST：加積分
    - GET：查詢時間範圍內積分
    """
    permission_classes = [IsAuthenticated, IsStudent]

    # =========================
    # POST → 加積分
    # =========================
    @swagger_auto_schema(
        operation_summary="加競技積分",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "score": openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description="要增加的積分（可為負數）"
                )
            },
            required=["score"]
        ),
        responses={
            200: openapi.Response(
                description="加分成功",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(type=openapi.TYPE_STRING),
                        "score": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "time": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            format=openapi.FORMAT_DATETIME
                        )
                    }
                )
            ),
            400: openapi.Response(description="參數錯誤"),
        },
        tags=["competition-score"]
    )
    def post(self, request):
        student = getattr(request.user, "student", None)
        if not student:
            return Response({"message": "無學生身分"}, status=403)

        score = request.data.get("score")
        if score is None:
            return Response({"message": "score 必填"}, status=400)

        try:
            score = int(score)
        except ValueError:
            return Response({"message": "score 必須是整數"}, status=400)

        record = CompetitionScore.objects.create(
            student=student,
            score=score,
            time=timezone.now()
        )

        return Response({
            "message": "積分已新增",
            "score": record.score,
            "time": record.time
        })
# 競技排行榜
class WeeklyCompetitionRankingAPIView(APIView):
    """
    當週競技積分排行榜（含與昨天比較）
    """
    permission_classes = [IsAuthenticated, IsStudent]

    @swagger_auto_schema(
        operation_summary="當週競技積分排行榜",
        manual_parameters=[
            openapi.Parameter(
                "scope",
                openapi.IN_QUERY,
                description="排名範圍：school（同校） / league（同聯盟）",
                type=openapi.TYPE_STRING,
                enum=["school", "league"],
                required=True
            )
        ],
        responses={
            200: openapi.Response(
                description="查詢成功",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "scope": openapi.Schema(type=openapi.TYPE_STRING),
                        "display_type": openapi.Schema(type=openapi.TYPE_STRING),
                        "display_name": openapi.Schema(type=openapi.TYPE_STRING),
                        "has_done_today": openapi.Schema(type=openapi.TYPE_BOOLEAN,description="今天是否已有競技積分紀錄"),
                        "week_range": openapi.Schema(type=openapi.TYPE_STRING),
                        "my_rank": openapi.Schema(type=openapi.TYPE_INTEGER, nullable=True),
                        "my_score": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "compare_yesterday": openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "rank_diff": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    description="與昨天相比名次變化（正數=進步，負數=退步）",
                                    nullable=True
                                ),
                                "score_diff": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    description="與昨天相比積分差異"
                                ),
                            }
                        ),
                        "top_30": openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    "rank": openapi.Schema(type=openapi.TYPE_INTEGER),
                                    "student_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                                    "student_name": openapi.Schema(type=openapi.TYPE_STRING),
                                    "school_name": openapi.Schema(type=openapi.TYPE_STRING),
                                    "score": openapi.Schema(type=openapi.TYPE_INTEGER),
                                }
                            )
                        )
                    }
                )
            )
        },
        tags=["competition-score"]
    )
    def get(self, request):
        student = getattr(request.user, "student", None)
        if not student:
            return Response({"message": "無學生身分"}, status=403)

        scope = request.query_params.get("scope")
        if scope not in ["school", "league"]:
            return Response({"message": "scope 參數錯誤"}, status=400)

        # ===== 1️⃣ 當週區間 =====
        today = timezone.localdate()
        yesterday = today - timezone.timedelta(days=1)

        week_start = today - timezone.timedelta(days=today.weekday())
        week_end = week_start + timezone.timedelta(days=6)

        # ===== 2️⃣ 取得同校 / 同聯盟學生 =====
        students_qs = Student.objects.all()
        display_name = None
        display_type = scope

        if scope == "school":
            students_qs = students_qs.filter(
                school_name=student.school_name,
                school_type=student.school_type
            )
            display_name = student.school_name

        elif scope == "league":
            league = League.objects.filter(
                school_name=student.school_name,
                school_type=student.school_type
            ).first()

            if not league:
                return Response({"message": "學生未加入任何聯盟"}, status=400)

            display_name = league.league_name

            league_school_names = League.objects.filter(
                league_name=league.league_name,
                school_type=league.school_type
            ).values_list("school_name", flat=True)

            students_qs = students_qs.filter(
                school_name__in=league_school_names,
                school_type=league.school_type
            )

        student_ids = students_qs.values_list("id", flat=True)

        # ===== 3️⃣ 排名計算 function =====
        def get_my_rank_and_score(date_from, date_to):
            scores = (
                CompetitionScore.objects.filter(
                    student_id__in=student_ids,
                    time__date__range=(date_from, date_to)
                )
                .values("student")
                .annotate(total_score=Sum("score"))
                .order_by("-total_score")
            )

            my_rank = None
            my_score = 0

            for idx, row in enumerate(scores, start=1):
                if row["student"] == student.id:
                    my_rank = idx
                    my_score = row["total_score"]
                    break

            return my_rank, my_score

        # ===== 4️⃣ 今天 / 昨天數據 =====
        today_rank, today_score = get_my_rank_and_score(week_start, today)
        yesterday_rank, yesterday_score = get_my_rank_and_score(week_start, yesterday)

        rank_diff = None
        score_diff = today_score - yesterday_score

        if today_rank and yesterday_rank:
            rank_diff = yesterday_rank - today_rank

        # ===== 5️⃣ 當週完整排行榜 =====
        scores = (
            CompetitionScore.objects.filter(
                student_id__in=student_ids,
                time__date__range=(week_start, week_end)
            )
            .values("student")
            .annotate(total_score=Sum("score"))
            .order_by("-total_score")
        )

        has_done_today = CompetitionScore.objects.filter(
            student=student,
            time__date=today
        ).exists()
        
        ranking = []
        student_map = {s.id: s for s in students_qs}

        for idx, row in enumerate(scores, start=1):
            stu = student_map.get(row["student"])
            if not stu:
                continue

            ranking.append({
                "rank": idx,
                "student_id": stu.id,
                "student_name": stu.student_name,
                "school_name": stu.school_name,
                "score": row["total_score"]
            })

        return Response({
            "scope": scope,
            "display_type": display_type,
            "display_name": display_name,
            "school_type" : student.school_type,
            "has_done_today": has_done_today,
            "week_range": f"{week_start} ~ {week_end}",
            "my_rank": today_rank,
            "my_score": today_score,
            "compare_yesterday": {
                "rank_diff": rank_diff,
                "score_diff": score_diff
            },
            "top_30": ranking[:30]
        })
        
class ImportExamPaperAPIView(APIView):
    """
    導入試卷題庫
    """
    @swagger_auto_schema(
    operation_summary="導入試卷題庫",
    operation_description="""
        導入試卷 JSON 題庫（支援 EngToChi / ChiToEng / Listening）

        📌 說明：
        - code：試卷代碼（唯一）
        - parts：題型區塊（EngToChi / ChiToEng / Listening）
        - 每個題型可包含多題
        - 考試時間自動設定為「明年 3/1 ~ 3/31」
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["code", "name", "level", "info", "parts"],
            properties={
                "code": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    example="ps-1"
                ),
                "name": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    example="國小英文測驗 1"
                ),
                "level": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    example="國小"
                ),
                "info": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    example="國小-1"
                ),
                "parts": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    additional_properties=openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            required=[
                                "id", "island", "unit", "level",
                                "type", "question_text",
                                "answer", "options"
                            ],
                            properties={
                                "id": openapi.Schema(
                                    type=openapi.TYPE_INTEGER,
                                    example=454
                                ),
                                "island": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="300字島"
                                ),
                                "unit": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="大城市島"
                                ),
                                "level": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="時尚大廳"
                                ),
                                "type": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="en_to_zh"
                                ),
                                "question_text": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="polite"
                                ),
                                "answer": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="有禮貌的"
                                ),
                                "explanation": openapi.Schema(
                                    type=openapi.TYPE_STRING,
                                    example="無題解"
                                ),
                                "options": openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        required=["id", "text"],
                                        properties={
                                            "id": openapi.Schema(
                                                type=openapi.TYPE_INTEGER,
                                                example=226
                                            ),
                                            "text": openapi.Schema(
                                                type=openapi.TYPE_STRING,
                                                example="有禮貌的"
                                            )
                                        }
                                    )
                                )
                            }
                        )
                    ),
                    example={
                        "EngToChi": [
                            {
                                "id": 454,
                                "island": "300字島",
                                "unit": "大城市島",
                                "level": "時尚大廳",
                                "type": "en_to_zh",
                                "question_text": "polite",
                                "options": [
                                    {"id": 226, "text": "有禮貌的"},
                                    {"id": 586, "text": "與…一樣"}
                                ],
                                "explanation": "無題解",
                                "answer": "有禮貌的"
                            }
                        ],
                        "ChiToEng": [],
                        "Listening": []
                    }
                )
            }
        ),
        responses={
            201: openapi.Response(
                description="導入成功",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="試卷導入成功"
                        ),
                        "exam_paper_id": openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            example=1
                        ),
                        "code": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            example="ps-1"
                        )
                    }
                )
            ),
            400: openapi.Response(
                description="資料格式錯誤"
            )
        },
        tags=["exam-paper"]
    )

    def post(self, request):
        serializer = ExamPaperImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # ===== 預設考試時間：明年 3/1 ~ 3/31 =====
        next_year = datetime.now().year + 1
        open_time = make_aware(datetime(next_year, 3, 1, 0, 0, 0))
        close_time = make_aware(datetime(next_year, 3, 31, 23, 59, 59))

        exam_paper, _ = ExamPaper.objects.get_or_create(
            code=data["code"],
            defaults={
                "name": data["name"],
                "level": data["level"],
                "info": data["info"],
                "open_time": open_time,
                "close_time": close_time,
            }
        )

        for part_key, questions in data["parts"].items():
            exam_part, _ = ExamPart.objects.get_or_create(
                exam_paper=exam_paper,
                part_key=part_key
            )

            for q in questions:
                question = ExamQuestion.objects.create(
                    exam_part=exam_part,
                    external_id=q["id"],
                    question_type=q["type"],
                    question_text=q["question_text"],
                    answer=q["answer"],
                    explanation=q["explanation"],
                    island=q["island"],
                    unit=q["unit"],
                    level=q["level"],
                )

                for opt in q["options"]:
                    ExamOption.objects.create(
                        question=question,
                        external_id=opt["id"],
                        description=opt["text"]
                    )

        return Response(
            {
                "message": "試卷導入成功",
                "exam_paper_id": exam_paper.id,
                "code": exam_paper.code
            },
            status=status.HTTP_201_CREATED
        )
        
class RetrieveExamPaperAPIView(APIView):

    def get(self, request):
        code = request.query_params.get("code")
        if not code:
            return Response({"message": "缺少 code"}, status=400)

        try:
            exam_paper = ExamPaper.objects.prefetch_related(
                "parts__questions__options"
            ).get(code=code)
        except ExamPaper.DoesNotExist:
            return Response({"message": "試卷不存在"}, status=404)

        now = timezone.now()
        if now < exam_paper.open_time or now > exam_paper.close_time:
            return Response({"message": "試卷尚未開放"}, status=403)

        serializer = ExamPaperRetrieveSerializer(exam_paper)
        return Response(serializer.data)    
        
class SubmitExamAPIView(APIView):
    """
    送出考試作答（每份試卷只能作答一次，自動計分）
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ExamSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # ===== 取得試卷 =====
        exam_paper = get_object_or_404(
            ExamPaper,
            code=data["code"]
        )

        now = timezone.now()
        if now < exam_paper.open_time or now > exam_paper.close_time:
            return Response(
                {"message": "考試未開放"},
                status=403
            )

        student = request.user.student

        # ===== 是否已作答過 =====
        if ExamRecord.objects.filter(
            student=student,
            exam_paper=exam_paper
        ).exists():
            return Response(
                {"message": "此試卷已作答過，每份試卷只能考一次"},
                status=403
            )

        # ===== 建立考試紀錄 =====
        exam_record = ExamRecord.objects.create(
            student=student,
            exam_paper=exam_paper,
            answer_time=now
        )

        # ===== 取出本試卷所有題目 =====
        questions = ExamQuestion.objects.filter(
            exam_part__exam_paper=exam_paper
        ).prefetch_related("options")

        question_map = {q.id: q for q in questions}

        total_questions = 0
        correct_count = 0

        # ===== 處理每一題作答 =====
        for ans in data["answers"]:
            q = question_map.get(ans["question_id"])
            if not q:
                # 非本試卷題目，直接忽略
                continue

            total_questions += 1

            selected_option = None
            selected_option_id = ans.get("selected_option_id")

            if selected_option_id:
                selected_option = q.options.filter(
                    id=selected_option_id
                ).first()

            # 🔥 關鍵：一定要是 True / False
            is_correct = False
            if selected_option:
                is_correct = selected_option.description == q.answer

            if is_correct:
                correct_count += 1

            ExamAnswerRecord.objects.create(
                exam_record=exam_record,
                question=q,
                selected_option=selected_option,
                selected_text=(
                    selected_option.description
                    if selected_option else ""
                ),
                correct_answer=q.answer,
                is_correct=is_correct
            )

        # ===== 計分 =====
        score = (
            int((correct_count / total_questions) * 100)
            if total_questions > 0 else 0
        )

        exam_record.score = score
        exam_record.save()

        return Response({
            "score": score,
            "total": total_questions,
            "correct": correct_count
        })

class ExamHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        code = request.query_params.get("code")
        if not code:
            return Response({"message": "缺少試卷編號"}, status=400)

        exam_paper = get_object_or_404(ExamPaper, code=code)
        student = request.user.student

        exam_record = ExamRecord.objects.filter(
            student=student,
            exam_paper=exam_paper
        ).first()

        if not exam_record:
            return Response({"message": "尚未作答此試卷"}, status=404)

        answers = ExamAnswerRecord.objects.filter(
            exam_record=exam_record
        ).select_related(
            "question",
            "question__exam_part",
            "selected_option"
        ).prefetch_related(
            "question__options"
        )

        parts = defaultdict(list)
        correct_count = 0

        for ans in answers:
            q = ans.question
            if ans.is_correct:
                correct_count += 1

            parts[q.exam_part.part_key].append({
                "question_id": q.id,  # 🔥 系統 id
                "question_text": q.question_text,
                "options": [
                    {
                        "id": opt.id,
                        "text": opt.description
                    }
                    for opt in q.options.all()
                ],
                "selected_option_id": (
                    ans.selected_option.id
                    if ans.selected_option else None
                ),
                "selected_text": ans.selected_text,
                "correct_answer": ans.correct_answer,
                "is_correct": ans.is_correct
            })

        return Response({
            "code": exam_paper.code,
            "exam_name": exam_paper.name,
            "score": exam_record.score,
            "answer_time": exam_record.answer_time,
            "summary": {
                "total": len(answers),
                "correct": correct_count,
                "wrong": len(answers) - correct_count
            },
            "questions": [
                {
                    "part_key": key,
                    "questions": value
                }
                for key, value in parts.items()
            ]
        })
        
class DashboardClassAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="班級／學校／聯盟統計總覽",
        operation_description="""
        依據角色回傳不同層級資料

        - teacher：班級 → 學生
        - school_admin：班級 → 學生
        - union_leader：學校總計
        - global_leader：聯盟 → 學校總計
        """
    )
    def get(self, request):
        user = request.user
        scope = DataScopeService(user)
        response_data = []

        # =========================
        # teacher / school_admin
        # =========================
        if user.role == "teacher":
            classes = scope.get_classes()

            for cls in classes:
                students_data = []
                for student in cls.students.all():
                    stats = StudentStatisticsService(student)
                    students_data.append({
                        "student_id": student.student_id,
                        "student_name": student.student_name,
                        "attendance_days": stats.attendance_days(),
                        "weekly_competition_score": stats.weekly_competition_score(),
                        "total_stars": stats.total_stars(),
                    })

                response_data.append({
                    "class_id": cls.id,
                    "class_name": f"{cls.grade}年{cls.classroom}班",
                    "school_name": cls.school_name,
                    "students": students_data
                })
                
        elif user.role == "school_admin":
            classes = scope.get_classes()
            school_map = {}
            for cls in classes:
                # 班級學生總計
                students = cls.students.all()
                total_attendance = sum(StudentStatisticsService(s).attendance_days() for s in students)
                total_weekly_score = sum(StudentStatisticsService(s).weekly_competition_score() for s in students)
                total_stars = sum(StudentStatisticsService(s).total_stars() for s in students)

                if cls.school_name not in school_map:
                    school_map[cls.school_name] = []

                school_map[cls.school_name].append({
                    "class_id": cls.id,
                    "class_name": f"{cls.grade}年{cls.classroom}班",
                    "attendance_days": total_attendance,
                    "weekly_competition_score": total_weekly_score,
                    "total_stars": total_stars
                })

            response_data = [
                {
                    "school_name": school_name,
                    "classes": classes
                }
                for school_name, classes in school_map.items()
            ]
        # =========================
        # union_leader（學校總計）
        # =========================
        elif user.role == "union_leader":
            leagues = scope.get_my_leagues()  # 已經拿到召集人自己聯盟下的所有 League

            # 用字典聚合
            league_map = {}

            for league in leagues:
                # 初始化該聯盟
                if league.league_name not in league_map:
                    league_map[league.league_name] = []

                # 每筆 League 代表一所學校
                school_name = league.school_name
                stats = StudentStatisticsService.get_school_total(school_name)

                league_map[league.league_name].append({
                    "school_name": school_name,
                    "attendance_days": stats["attendance_days"],
                    "weekly_competition_score": stats["weekly_competition_score"],
                    "total_stars": stats["total_stars"],
                })

            # 轉成列表回傳
            response_data = [
                {
                    "league_name": league_name,
                    "schools": schools
                }
                for league_name, schools in league_map.items()
            ]

            return Response(response_data)

        # =========================
        # global_leader（聯盟 → 學校總計）
        # =========================
        elif user.role == "global_leader":
            leagues = scope.get_all_leagues()

            for league in leagues:
                league_data = {
                    "league_name": league.league_name,
                    "schools": []
                }

                schools = League.objects.filter(
                    league_name=league.league_name
                ).values("school_name").distinct()

                for school in schools:
                    stats = StudentStatisticsService.get_school_total(
                        school["school_name"]
                    )

                    league_data["schools"].append({
                        "school_name": school["school_name"],
                        "attendance_days": stats["attendance_days"],
                        "weekly_competition_score": stats["weekly_competition_score"],
                        "total_stars": stats["total_stars"],
                    })

                response_data.append(league_data)
        return Response(response_data)

class StudentDetailDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="學生詳細學習統計",
        operation_description="""
        學生查看自己的詳細學習統計資料，包括出勤、競賽分數、星星數及考試分數。

        **限制角色**：
        - 只有學生(student)可以存取

        **回傳欄位**：
        - student_name：學生姓名
        - school_name：學校名稱
        - class_name：班級顯示，例如 3年2班
        - attendance_days：出勤天數
        - weekly_competition_score：每週競賽分數
        - total_stars：總星星數
        - island_stars：各島嶼星星數
        - exam_scores：考試成績
        """,
        responses={200: openapi.Response(
            description="學生詳細統計資料",
            examples={
                "application/json": {
                    "student_name": "王小明",
                    "school_name": "幸福國小",
                    "class_name": "3年2班",
                    "attendance_days": 30,
                    "weekly_competition_score": 120,
                    "total_stars": 85,
                    "island_stars": {
                        "Island1": 40,
                        "Island2": 45
                    },
                    "exam_scores": [
                        {
                            "exam_paper__name": "單字測驗",
                            "score": 90
                        }
                    ]
                }
            }
        )}
    )
    def get(self, request):
        user = request.user

        # 1️⃣ 限制角色
        if user.role != "student":
            return Response({"detail": "僅限學生存取"}, status=403)

        # 2️⃣ 從 user 取得 student
        try:
            student = user.student
        except Student.DoesNotExist:
            return Response({"detail": "學生資料不存在"}, status=404)

        student_class = student.student_class
        class_display = f"{student_class.grade}年{student_class.classroom}班"

        # 3️⃣ 計算統計
        stats = StudentStatisticsService(student)

        return Response({
            "student_name": student.student_name,
            "school_name": student.school_name,  # 或 student_class.school_name
            "school_type": student.school_type, 
            "class_name": class_display,
            "attendance_days": stats.attendance_days(),
            "weekly_competition_score": stats.weekly_competition_score(),
            "total_stars": stats.total_stars(),
            "island_stars": stats.island_stars(),
            "exam_scores": list(stats.exam_scores())
        })

class StudentAchievementCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="學生紀錄完成成就",
        operation_description="學生完成某個成就時呼叫此 API，後端只負責記錄完成時間，成就名稱由前端傳入",
        request_body=StudentAchievementCreateSerializer,
        responses={
            201: StudentAchievementSerializer,
            200: "成就已完成，無須重複紀錄",
            403: "僅限學生使用"
        },
        tags=["Achievement"]
    )
    def post(self, request):
        user = request.user

        if user.role != "student":
            return Response({"detail": "僅限學生"}, status=403)

        student = user.student

        serializer = StudentAchievementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        obj, created = StudentAchievement.objects.get_or_create(
            student=student,
            name=serializer.validated_data["name"]
        )

        return Response(
            StudentAchievementSerializer(obj).data,
            status=201 if created else 200
        )

class StudentAchievementListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="學生已完成成就列表",
        operation_description="列出學生已完成的成就及完成時間",
        responses={200: StudentAchievementSerializer(many=True)},
        tags=["Achievement"]
    )
    def get(self, request):
        if request.user.role != "student":
            return Response({"detail": "僅限學生"}, status=403)

        student = request.user.student

        achievements = StudentAchievement.objects.filter(student=student).order_by("-completed_at")
        serializer = StudentAchievementSerializer(achievements, many=True)
        return Response(serializer.data)


