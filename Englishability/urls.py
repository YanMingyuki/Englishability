from django.contrib import admin
from django.urls import path, re_path, include
from django.views.static import serve
from django.urls import re_path
from rest_framework.permissions import AllowAny
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.contrib import admin
from django.urls import path

from students.views import OIDCCallbackView, OIDCLoginView

schema_view = get_schema_view(
   openapi.Info(
      title="Englishability API",
      default_version='v1',
      description="API 文件",
      contact=openapi.Contact(email="support@example.com"),
   ),
   public=True,
   permission_classes=(AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/questionbank/', include('questionbank.urls')),
    path('api/students/', include('students.urls')), 
    path('api/swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/oidclogin/', OIDCLoginView.as_view(), name='oidc-login'),
    path('api/oidccallback/', OIDCCallbackView.as_view(), name='oidc-callback'),
]