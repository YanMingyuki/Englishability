from django.urls import path, include
from questionbank.views import CheckAnswerAPIView, GenerateQuestionsAPIView, ImportOptionView, ImportQuestionView
from rest_framework.routers import DefaultRouter
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.permissions import AllowAny
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

router = DefaultRouter()


urlpatterns = [
    path('', include(router.urls)),
    path('generate/', GenerateQuestionsAPIView.as_view(), name='generate-questions'),
    path('check/', CheckAnswerAPIView.as_view(), name='check-answer'),
    path("import/options/", ImportOptionView.as_view()),
    path("import/questions/", ImportQuestionView.as_view()),
]   

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
