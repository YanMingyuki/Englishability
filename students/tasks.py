# accounts/tasks.py

from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings


@shared_task
def send_reset_password_email(to_emails, student_name, student_id, reset_url):
    subject = f"[學生忘記密碼通知] {student_name}（{student_id}）"
    message = (
        f"學生 {student_name}（{student_id}）請求重設密碼。\n"
        f"請點擊以下連結為學生重設密碼：\n{reset_url}\n\n"
        "此連結僅限授課老師使用。"
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        to_emails,
        fail_silently=False,
    )
