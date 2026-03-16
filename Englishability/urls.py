from django.contrib import admin
from django.urls import path, re_path, include
from django.views.static import serve
from django.urls import re_path
from rest_framework.permissions import AllowAny
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.contrib import admin
from django.urls import path
from mozilla_django_oidc import views as oidc_views

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
    # OIDC login
    # 登入
    path("api/oidc/login/", oidc_views.OIDCAuthenticationRequestView.as_view(), name="oidc_authentication_init"),
    # 回調
    path("api/oidccallback/", oidc_views.OIDCAuthenticationCallbackView.as_view(), name="oidc_authentication_callback"),
    # 登出
    path("api/oidc/logout/", oidc_views.OIDCLogoutView.as_view(), name="oidc_logout"),
]