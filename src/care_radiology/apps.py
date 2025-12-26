from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

PLUGIN_NAME = "care_radiology"


class CareRadiologyPluginConfig(AppConfig):
    name = PLUGIN_NAME
    verbose_name = _("Care radiology plugin")

    def ready(self):
        import care_radiology.signals  # noqa F401
