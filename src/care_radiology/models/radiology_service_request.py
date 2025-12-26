from django.db import models
from care.emr.models import EMRBaseModel
from care.emr.models.service_request import ServiceRequest
from care_radiology.models.dicom_study import DicomStudy


class RadiologyServiceRequest(EMRBaseModel):
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name="radiology_service_requests",
        null=True,
    )
    dicom_study = models.ForeignKey(
        DicomStudy,
        on_delete=models.CASCADE,
        related_name="dicom_studies",
        null=True,
    )
    raw_data = models.JSONField()

    class Meta:
        db_table = "radiology_servicerequest"
        models.UniqueConstraint(
            fields=["service_request", "dicom_study"],
            name="unique_service_request_dicom_study",
        )
