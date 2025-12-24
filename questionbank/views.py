from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from students.models import TestRecord
from students.tokens import IsStudent
from .models import Question, QuestionOptionEN, QuestionOptionLetter, QuestionOptionZH, QuestionType
from .serializers import ImportOptionSerializer, ImportQuestionSerializer, QuestionSerializer, QuestionWithAnswerSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.parsers import MultiPartParser, FormParser
import pandas as pd
import math
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated

OPTION_MODEL_MAP = {
    "zh_to_en": QuestionOptionEN,
    "cloze": QuestionOptionEN,
    "en_to_zh": QuestionOptionZH,
    "letter": QuestionOptionLetter,
}

QUESTION_TYPE_MAP = {
    "中翻英": "zh_to_en",
    "英翻中": "en_to_zh",
    "克漏字": "cloze",
    "字母": "letter",
}

class GenerateQuestionsAPIView(APIView):
    """
    功能：
    - 根據關卡 / 單元 / 島嶼 / 題型 / 題數生成題目
    - 若有指定題型，只會從該題型題目中抽題
    - include_answer 控制是否回傳答案
    """

    @swagger_auto_schema(
        operation_summary="生成題目",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                '關卡': openapi.Schema(type=openapi.TYPE_STRING),
                '單元': openapi.Schema(type=openapi.TYPE_STRING),
                '島嶼': openapi.Schema(type=openapi.TYPE_STRING),
                '題數': openapi.Schema(type=openapi.TYPE_INTEGER),
                '題型': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=list(QUESTION_TYPE_MAP.keys())
                ),
                'include_answer': openapi.Schema(type=openapi.TYPE_BOOLEAN),
            }
        ),
        responses={200: QuestionSerializer(many=True)},
        tags=['questionbank']
    )
    def post(self, request):
        data = request.data

        level = data.get('關卡')
        unit = data.get('單元')
        island = data.get('島嶼')
        num = data.get('題數', 10)
        include_answer = data.get('include_answer', False)

        # 題型（可選）
        type_str = QUESTION_TYPE_MAP.get(data.get('題型'))

        queryset = Question.objects.all()

        # ① 範圍限制
        if level:
            queryset = queryset.filter(level=level)
        if unit:
            queryset = queryset.filter(unit=unit)
        if island:
            queryset = queryset.filter(island=island)

        # ② 題型限制（如果有）
        if type_str:
            queryset = queryset.filter(type=type_str)

        # ③ 隨機抽題
        queryset = queryset.order_by('?')[:num]

        serializer_cls = (
            QuestionWithAnswerSerializer
            if include_answer
            else QuestionSerializer
        )

        serializer = serializer_cls(
            queryset,
            many=True,
            context={'type_str': type_str}
        )

        return Response(serializer.data)


class CheckAnswerAPIView(APIView):
    """
    功能：
    - 前端提交多題答案
    - 回傳每題是否正確
    - 未作答(null)視為錯誤
    - 回傳：題目、正確答案、作答答案、題解
    - 建立學生答題紀錄
    - 星數最多 5 星，取下限
    """
    permission_classes = [IsAuthenticated, IsStudent]

    @swagger_auto_schema(
        operation_summary="測驗批改（不建立學生作答紀錄）",
        operation_description="檢查多題答案是否正確，並紀錄學生作答結果",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
                    properties={
            'stage': openapi.Schema(
                type=openapi.TYPE_STRING,
                description="關卡/年級（前端傳什麼就存什麼）",
                example="國小-1"
            ),
            'unit': openapi.Schema(
                type=openapi.TYPE_STRING,
                description="單元名稱",
                example="大城市島"
            ),
            'island': openapi.Schema(
                type=openapi.TYPE_STRING,
                description="島嶼名稱",
                example="300字島"
            ),
            'answers': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'question_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                        'option_id': openapi.Schema(
                            type=openapi.TYPE_INTEGER,
                            nullable=True,
                            description="未作答請傳 null"
                        ),
                    }
                )
            )
        },
        required=["answers"]
        ),
        responses={200: openapi.Response(
            description='result',
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'results': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'question_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'question_text': openapi.Schema(type=openapi.TYPE_STRING),
                            'selected_option': openapi.Schema(type=openapi.TYPE_STRING, nullable=True),
                            'correct_answer': openapi.Schema(type=openapi.TYPE_STRING),
                            'is_correct': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'explanation': openapi.Schema(type=openapi.TYPE_STRING),
                        }
                    )),
                    'summary': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'correct_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'total_questions': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'correct_ratio': openapi.Schema(type=openapi.TYPE_STRING),
                            'stars': openapi.Schema(type=openapi.TYPE_INTEGER),
                        }
                    )
                }
            )
        )},
        tags=['questionbank']
    )
    def post(self, request):
        answers = request.data.get('answers')

        if not isinstance(answers, list):
            return Response({"error": "answers 必須是陣列"}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        student = getattr(user, 'student', None)
        if not student:
            return Response({"error": "無法取得學生資訊"}, status=status.HTTP_403_FORBIDDEN)

        results = []
        correct_count = 0
        total_questions = len(answers)
        island = unit = stage = ""

        for ans in answers:
            question_id = ans.get('question_id')
            option_id = ans.get('option_id')

            try:
                question = Question.objects.get(id=question_id)
            except Question.DoesNotExist:
                results.append({
                    'question_id': question_id,
                    'question_text': '題目不存在',
                    'selected_option': None,
                    'correct_answer': '無',
                    'is_correct': False,
                    'explanation': '無題解'
                })
                continue
            
            selected_option = None
            correct_answer = "未知"

            try:
                if question.type in ['zh_to_en', 'cloze']:
                    correct_answer = QuestionOptionEN.objects.get(
                        id=question.correct_option_id
                    ).text
                    if option_id:
                        selected_option = QuestionOptionEN.objects.get(id=option_id).text

                elif question.type == 'en_to_zh':
                    correct_answer = QuestionOptionZH.objects.get(
                        id=question.correct_option_id
                    ).text
                    if option_id:
                        selected_option = QuestionOptionZH.objects.get(id=option_id).text

                elif question.type == 'letter':
                    correct_answer = QuestionOptionLetter.objects.get(
                        id=question.correct_option_id
                    ).letter
                    if option_id:
                        selected_option = QuestionOptionLetter.objects.get(id=option_id).letter
            except:
                pass

            is_correct = option_id is not None and option_id == question.correct_option_id
            if is_correct:
                correct_count += 1

            results.append({
                'question_id': question.id,
                'question_text': question.question_text,
                'selected_option': selected_option,
                'correct_answer': correct_answer,
                'is_correct': is_correct,
                'explanation': question.explanation or '無題解'
            })

        stars = min(5, math.floor(correct_count / total_questions * 5)) if total_questions else 0
        correct_ratio = f"{correct_count}/{total_questions}"
        stage = request.data.get("stage", "")
        unit = request.data.get("unit", "")
        island = request.data.get("island", "")
        
        TestRecord.objects.create(
            student=student,
            answer_time=timezone.now(),
            score=correct_count,
            stars=stars,
            correct_ratio=correct_ratio,
            stage=stage,
            unit=unit,
            island=island
        )

        return Response({
            'results': results,
            'summary': {
                'correct_count': correct_count,
                'total_questions': total_questions,
                'correct_ratio': correct_ratio,
                'stars': stars
            }
        })
class ImportOptionView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_summary="匯入選項池",
        request_body=ImportOptionSerializer
    )
    def post(self, request):
        serializer = ImportOptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        item = serializer.validated_data["item"]
        file = serializer.validated_data["file"]

        model = OPTION_MODEL_MAP[item]

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        if not {"編號", "內容"}.issubset(df.columns):
            return Response(
                {"detail": "Excel 必須包含「編號、內容」欄位"},
                status=400
            )

        for i, row in df.iterrows():
            option_id = int(row["編號"])
            content = str(row["內容"]).strip()

            if model == QuestionOptionLetter:
                model.objects.update_or_create(
                    id=option_id,
                    defaults={"letter": content}
                )
            else:
                model.objects.update_or_create(
                    id=option_id,
                    defaults={"text": content}
                )

        return Response({"detail": f"{item} 選項匯入完成"})
    
class ImportQuestionView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_summary="匯入題目",
        request_body=ImportQuestionSerializer
    )
    def post(self, request):
        serializer = ImportQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file = serializer.validated_data["file"]

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()

        required = {
            "島嶼", "單元", "關卡",
            "題型", "題目", "正確答案"
        }
        missing = [c for c in required if c not in df.columns]
        if missing:
            return Response(
                {"detail": "Excel 缺少必要欄位", "missing": missing},
                status=400
            )

        for i, row in df.iterrows():
            raw_type = str(row["題型"]).strip()

            # 🔑 中文 → code
            type_code = QUESTION_TYPE_MAP.get(raw_type)
            if not type_code:
                return Response(
                    {"detail": f"第 {i+2} 列題型不支援：{raw_type}"},
                    status=400
                )

            Question.objects.create(
                island=row["島嶼"],
                unit=row["單元"],
                level=row["關卡"],
                type=type_code,
                question_text=row["題目"],
                correct_option_id=int(row["正確答案"]),
                explanation=row.get("題解", "")
            )

        return Response({"detail": "題目匯入完成"})