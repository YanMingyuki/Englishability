from django.db import models


# ============================
# 1. 題型 (固定四種)
# ============================
class QuestionType(models.TextChoices):
    ZH_TO_EN = 'zh_to_en', '中翻英'
    EN_TO_ZH = 'en_to_zh', '英翻中'
    CLOZE = 'cloze', '克漏字'
    LETTER = 'letter', '字母'


# ============================
# 2. 題目表（主表）
# ============================
class Question(models.Model):
    island = models.CharField(max_length=50)
    unit = models.CharField(max_length=50)
    level = models.CharField(max_length=50)

    # 題型使用固定choices
    type = models.CharField(
        max_length=20,
        choices=QuestionType.choices
    )

    question_text = models.TextField()

    # 正確選項ID：依照題型指向不同選項池的 id
    correct_option_id = models.IntegerField()

    explanation = models.TextField(blank=True, null=True)  # 題解

    def __str__(self):
        return f"{self.type} - {self.level} - {self.question_text[:20]}"


# ============================
# 3. 英文選項池 (中翻英 & 克漏字)
# ============================
class QuestionOptionEN(models.Model):
    text = models.CharField(max_length=255)

    def __str__(self):
        return self.text


# ============================
# 4. 中文選項池 (英翻中)
# ============================
class QuestionOptionZH(models.Model):
    text = models.CharField(max_length=255)

    def __str__(self):
        return self.text


# ============================
# 5. 字母選項池 (字母題型)
# ============================
class QuestionOptionLetter(models.Model):
    letter = models.CharField(max_length=5)  # A~Z

    def __str__(self):
        return self.letter
