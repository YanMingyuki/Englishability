from rest_framework import serializers
from .models import Question, QuestionOptionEN, QuestionOptionZH, QuestionOptionLetter
import random

# -----------------------------
# 基本選項序列化
# -----------------------------
class QuestionOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()


# -----------------------------
# 題目序列化（不含答案）
# -----------------------------
class QuestionSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            'id',
            'island',
            'unit',
            'level',
            'type',
            'question_text',
            'options',
            'explanation',
        ]

    def get_options(self, obj):
        """
        依題型決定選項來源
        抽 3 個干擾選項 + 1 個正確選項
        """

        if obj.type in ['zh_to_en', 'cloze']:
            option_model = QuestionOptionEN
            text_attr = 'text'
        elif obj.type == 'en_to_zh':
            option_model = QuestionOptionZH
            text_attr = 'text'
        elif obj.type == 'letter':
            option_model = QuestionOptionLetter
            text_attr = 'letter'
        else:
            return []

        # 正確選項
        correct_option = option_model.objects.get(
            id=obj.correct_option_id
        )

        # 干擾選項（全系統同題型）
        distractors_qs = option_model.objects.exclude(
            id=correct_option.id
        )

        distractors = random.sample(
            list(distractors_qs),
            k=min(3, distractors_qs.count())
        )

        final_options = distractors + [correct_option]
        random.shuffle(final_options)

        return [
            {
                'id': opt.id,
                'text': getattr(opt, text_attr)
            }
            for opt in final_options
        ]


# -----------------------------
# 題目序列化（含答案）
# -----------------------------
class QuestionWithAnswerSerializer(QuestionSerializer):
    answer = serializers.SerializerMethodField()

    class Meta(QuestionSerializer.Meta):
        fields = QuestionSerializer.Meta.fields + ['answer']

    def get_answer(self, obj):
        if obj.type in ['zh_to_en', 'cloze']:
            return QuestionOptionEN.objects.get(
                id=obj.correct_option_id
            ).text
        elif obj.type == 'en_to_zh':
            return QuestionOptionZH.objects.get(
                id=obj.correct_option_id
            ).text
        elif obj.type == 'letter':
            return QuestionOptionLetter.objects.get(
                id=obj.correct_option_id
            ).letter
        return None

class ImportOptionSerializer(serializers.Serializer):
    item = serializers.ChoiceField(
        choices=[
            ("zh_to_en", "中翻英"),
            ("cloze", "克漏字"),
            ("en_to_zh", "英翻中"),
            ("letter", "字母"),
        ]
    )
    file = serializers.FileField()
    
class ImportQuestionSerializer(serializers.Serializer):
    file = serializers.FileField()

