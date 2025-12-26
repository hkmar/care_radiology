from django.conf import settings
import requests

from enum import Enum
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.cache import cache

from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

from care.emr.models.patient import Patient
from care_radiology.models.radiology_service_request import RadiologyServiceRequest
from care_radiology.models.dicom_study import DicomStudy


DCM4CHEE_BASEURL = settings.PLUGIN_CONFIGS['care_radiology']['DCM4CHEE_DICOMWEB_BASEURL']


class DICOM_TAG(Enum):
    # Study Tags
    StudyInstanceUID = "0020000D"
    StudyModalities = "00080061"
    StudyDescription = "00081030"
    StudyDate = "00080020"
    StudyTime = "00080030"

    # Series Tags
    SeriesInstanceUID = "0020000E"
    SeriesModality = "00080060"
    SeriesNumber = "00200011"
    NumberOfSeriesRelatedInstances = "00201209"
    SeriesDescription = "0008103E"

    # Instance Tags
    SOPInstanceUID = "00080018"
    ReferencedInstanceUID = "00081155"

    ReferencedSOPSQ = "00081199"


class DicomViewSet(ViewSet):

    # A dummy API for JWT verification called by nginx-proxy for dicomweb requests
    @action(detail=False, methods=["get"], url_path="authenticate")
    def authenticate(self, _):
        return Response(status=200)

    # DCM Files upload
    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        patient = Patient.objects.get(external_id=request.data.get("patient_id"))
        dcm_file = request.FILES.get("file")

        if not dcm_file:
            return Response({"error": "No file provided"}, status=400)

        try:
            body, content_type = encode_file_multipart_related(dcm_file)
            upload_response = requests.post(
                url=f"{DCM4CHEE_BASEURL}/rs/studies",
                data=body,
                headers={
                    "Content-Type": content_type,
                    "Accept": "application/dicom+json",
                },
            )
            if upload_response.status_code in [200, 201]:
                refenrenced_sop = d_find(
                    upload_response.json(), DICOM_TAG.ReferencedSOPSQ.value
                )[0]

                instance_uid = d_find(
                    refenrenced_sop, DICOM_TAG.ReferencedInstanceUID.value
                )[0]

                study_uid = d_find(
                    d_query_instance(instance_uid), DICOM_TAG.StudyInstanceUID.value
                )[0]

                DicomStudy.objects.update_or_create(
                    dicom_study_uid=study_uid,
                    patient=patient,
                    defaults={},
                )

                # Bust the study from cache
                key = f"radiology:dicom:study:{study_uid}"
                cache.delete(key)

                return Response(
                    data={
                        "message": "DICOM file uploaded to Orthanc successfully",
                        "study_uid": study_uid,
                        "study": fetch_study(study_uid),
                    },
                    status=201,
                )

            else:
                return Response(
                    data={
                        "error": "Failed to upload to Orthanc",
                        "status_code": upload_response.text,
                        "status_code": upload_response.status_code,
                    },
                    status=502,
                )

        except Exception as e:
            return Response(
                data={"error": "Exception occurred", "details": str(e)}, status=500
            )

    # Get list of studies
    @action(detail=False, methods=["get"], url_path="studies")
    def get_studies(self, request):
        patient_external_id = request.query_params.get("patientId")
        studies = DicomStudy.objects.filter(patient__external_id=patient_external_id)

        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_study = {
                executor.submit(fetch_study, study.dicom_study_uid): study
                for study in studies
            }
            for future in as_completed(future_to_study):
                result = future.result()
                if result is not None:
                    results.append(result)

        return Response(results, status=200)

    @action(
        detail=False,
        methods=["get"],
        url_path="service-requests",
        authentication_classes=[],
        permission_classes=[AllowAny],
    )
    def get_servicerequests(self, request):
        service_request_external_id = request.query_params.get("serviceRequestId")
        tsr = RadiologyServiceRequest.objects.filter(
            service_request__external_id=service_request_external_id,
            dicom_study__dicom_study_uid__isnull=False,
        )

        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_study = {
                executor.submit(fetch_study, r.dicom_study.dicom_study_uid): r
                for r in tsr
            }

            for future in as_completed(future_to_study):
                results.append(future.result())

        return Response(
            results,
            status=200,
        )


def fetch_study(study_uid):
    key = f"radiology:dicom:study:{study_uid}"
    cached = cache.get(key)
    if cached:
        return cached

    study = d_query_study(study_uid)

    if study is None:
        return None

    series = [
        {
            "series_uid": d_find(s, DICOM_TAG.SeriesInstanceUID.value)[0],
            "series_number": d_find(s, DICOM_TAG.SeriesNumber.value),
            "series_instance_count": d_find(
                s, DICOM_TAG.NumberOfSeriesRelatedInstances.value
            ),
            "series_description": d_find(s, DICOM_TAG.SeriesDescription.value),
            "series_modality": d_find(s, DICOM_TAG.SeriesModality.value),
        }
        for s in d_query_series_for_study(study_uid)
    ]

    study_description = (
        d_find(study, DICOM_TAG.StudyDescription.value)[0]
        if len(d_find(study, DICOM_TAG.StudyDescription.value)) > 0
        else None
    )

    study_date = d_datetime_to_iso(
        d_find(study, DICOM_TAG.StudyDate.value)[0],
        d_find(study, DICOM_TAG.StudyTime.value)[0],
    )

    cachable = {
        "study_uid": study_uid,
        "study_date": study_date,
        "study_description": study_description,
        "study_modalities": d_find(study, DICOM_TAG.StudyModalities.value),
        "study_series": series,
    }

    cache.set(key, cachable, timeout=60 * 60)
    return cachable


# Dicom Web Utilities ---------------------------------------------------------
def d_query_instance(instance_id):
    response = requests.get(
        url=f"{DCM4CHEE_BASEURL}/rs/instances",
        headers={
            "Accept": "application/json",
        },
        params={"SOPInstanceUID": instance_id},
    )

    if not response.ok:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    if isinstance(data, list) and data:
        return data[0]

    return None


def d_query_series_for_study(study_id):
    response = requests.get(
        url=f"{DCM4CHEE_BASEURL}/rs/studies/{study_id}/series",
        headers={
            "Accept": "application/json",
        },
    )

    if not response.ok:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    if data:
        return data
    else:
        return None


def d_query_study(study_uid):
    response = requests.get(
        url=f"{DCM4CHEE_BASEURL}/rs/studies",
        headers={
            "Accept": "application/json",
        },
        params={
            "StudyInstanceUID": study_uid,
            "includefield": f"{DICOM_TAG.StudyDescription.value},{DICOM_TAG.StudyModalities.value}",
        },
    )

    if not response.ok:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    if isinstance(data, list) and data:
        return data[0]

    return None


def d_find(data: any, key):
    results = []
    if isinstance(data, dict):
        if key in data:
            results.extend(data[key].get("Value", []))
        for v in data.values():
            results.extend(d_find(v, key))
    elif isinstance(data, list):
        for item in data:
            results.extend(d_find(item, key))

    return results


def d_datetime_to_iso(da, tm=None):
    if not da:
        return None

    # Parse date
    year = int(da[0:4])
    month = int(da[4:6])
    day = int(da[6:8])

    if tm:
        # Parse time (HHMMSS[.ffffff])
        hours = int(tm[0:2])
        minutes = int(tm[2:4])
        seconds = int(tm[4:6])
        microseconds = 0

        if "." in tm:
            fraction = tm.split(".")[1]
            fraction = (fraction + "000000")[:6]
            microseconds = int(fraction)

        dt = datetime(year, month, day, hours, minutes, seconds, microseconds)
    else:
        dt = datetime(year, month, day)

    return dt.isoformat()


# Multipart Related Encoder ---------------------------------------------------
def encode_file_multipart_related(file_obj):
    import uuid

    # filename = file_obj.name

    boundary = f"DICOMBOUNDARY-{uuid.uuid4().hex}"
    file_bytes = file_obj.read()

    body = (
        (
            f"--{boundary}\r\n"
            f"Content-Type: application/dicom\r\n"
            f"Content-Length: {len(file_bytes)}\r\n"
            f"\r\n"
        ).encode("utf-8")
        + file_bytes
        + f"\r\n--{boundary}--\r\n".encode("utf-8")
    )

    content_type = f'multipart/related; type="application/dicom"; boundary={boundary}'

    return body, content_type
