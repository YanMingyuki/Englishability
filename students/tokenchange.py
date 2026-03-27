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
                "code": openapi.Schema(type=openapi.TYPE_STRING),
                "redirect_uri": openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
        responses={200: "成功", 400: "錯誤"}
    )
    def post(self, request):
        code = request.data.get("code")
        redirect_uri = request.data.get("redirect_uri")

        if not code or not redirect_uri:
            return Response({"error": "missing params"}, status=400)

        token_url = "https://oidc.kh.edu.tw/oauth2/token"

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,

            # 🔒 後端保護
            "client_id": "你的client_id",
            "client_secret": "你的client_secret",
        }

        try:
            res = requests.post(
                token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            return Response(res.json(), status=res.status_code)

        except Exception as e:
            return Response({"error": str(e)}, status=500)