import base64
import requests

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


class OIDCTokenView(APIView):

    @swagger_auto_schema(
        operation_summary="OIDC Code 換 Token",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["code", "redirect_uri"],
            properties={
                "code": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="OIDC 回傳的 code"
                ),
                "redirect_uri": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="必須與當初登入完全一致"
                ),
            },
        ),
        responses={
            200: openapi.Response("成功"),
            400: "參數錯誤",
            500: "伺服器錯誤"
        }
    )
    def post(self, request):

        code = request.data.get("code")
        redirect_uri = request.data.get("redirect_uri")

        if not code or not redirect_uri:
            return Response(
                {"error": "missing params"},
                status=status.HTTP_400_BAD_REQUEST
            )

        token_url = "https://oidc.kh.edu.tw/oauth2/token"

        # 🔥 你的 client 資訊（只放後端）
        client_id = "kh_vendor_englishability_a95da8c087d6f9c3f62acc5e22c26f42"
        client_secret = "38efe712ebe3b6af5d7365441cf2e4d5b6d3c9dc07aa977f74d8f1c8e6c134d1"

        # ✅ 關鍵：使用 Basic Auth（解決 invalid_client）
        basic_auth = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic_auth}"
        }

        try:
            res = requests.post(
                token_url,
                data=payload,
                headers=headers,
                timeout=10
            )

            return Response(res.json(), status=res.status_code)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )