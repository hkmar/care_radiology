from django.conf import settings
from django.shortcuts import HttpResponse
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from care_radiology.api.dicom import DicomViewSet
from care_radiology.api.webhooks import WebhookViewSet


def healthy(request):
    return HttpResponse("OK")


router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("webhooks", WebhookViewSet, basename="webhooks")
router.register("dicom", DicomViewSet, basename="radiology")

urlpatterns = [
    path("health", healthy),
] + router.urls
