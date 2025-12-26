from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, ParseError


from care.emr.models.patient import Patient
from care.emr.models.service_request import ServiceRequest
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.webhook_logs import RadiologyWebhookLogs
from care_radiology.models.radiology_service_request import RadiologyServiceRequest

STATIC_API_KEY = settings.PLUGIN_CONFIGS['care_radiology']['WEBHOOK_SECRET']


class StaticAPIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get("Authorization")
        if api_key == STATIC_API_KEY:
            return (AnonymousUser(), None)
        raise AuthenticationFailed("Invalid API key")


class WebhookViewSet(ViewSet):
    @action(
        detail=False,
        methods=["post"],
        url_path="study",
        authentication_classes=[StaticAPIKeyAuthentication],
        permission_classes=[AllowAny],
    )
    def save_webhook(self, request):
        try:
            data = request.data
        except ParseError:
            return Response(
                {"detail": "Invalid JSON payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        RadiologyWebhookLogs.objects.create(raw_data=data, type="SR-STUDY-INSERT")
        if not isinstance(data, dict):
            return Response(
                {"detail": "JSON object expected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if data.get("service_request_id") and data.get("study_id"):
            try:
                sr = ServiceRequest.objects.get(external_id=data["service_request_id"])
            except ServiceRequest.DoesNotExist:
                return Response(
                    {"detail": "No matching service request"},
                    status=status.HTTP_200_OK,
                )
            (study, ds_created) = DicomStudy.objects.get_or_create(
                dicom_study_uid=data.get("study_id"), patient=sr.patient, defaults={}
            )
            if sr and study:
                (rsr, rsr_created) = RadiologyServiceRequest.objects.update_or_create(
                    service_request=sr, dicom_study=study, defaults={"raw_data": data}
                )

            return Response(
                {
                    "detail": "Webhook received and saved successfully",
                    "record": {
                        "external_id": rsr.external_id,
                        "data": rsr.raw_data,
                    },
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "detail": "Webhook received and saved successfully",
            },
            status=status.HTTP_200_OK,
        )
