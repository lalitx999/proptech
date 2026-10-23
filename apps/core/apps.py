import sys
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core Marketplace & SEO'

    def ready(self):
        # Python 3.14 compatibility: super() proxy copy fix for Django template Context
        if sys.version_info >= (3, 14):
            from django.template.context import BaseContext
            def _compat_base_context_copy(self):
                obj = self.__class__.__new__(self.__class__)
                obj.dicts = self.dicts[:]
                return obj
            BaseContext.__copy__ = _compat_base_context_copy
