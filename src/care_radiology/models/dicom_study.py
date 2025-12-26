from django.db import models
from care.emr.models import EMRBaseModel
from care.emr.models.patient import Patient


class DicomStudy(EMRBaseModel):
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="dicom_studies"
    )
    dicom_study_uid = models.CharField(max_length=500)

    class Meta:
        db_table = "radiology_dicomstudy"
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "dicom_study_uid"], name="unique_patient_study_uid"
            )
        ]
