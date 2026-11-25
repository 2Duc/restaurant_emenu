from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        from django.db.models.signals import post_delete, post_save
        from .models import Category, MenuItem, Review
        from .views.menu_view import bump_menu_cache
        for model in (Category, MenuItem, Review):
            post_save.connect(lambda **kw: bump_menu_cache(), sender=model, weak=False, dispatch_uid=f'menu_cache_save_{model.__name__}')
            post_delete.connect(lambda **kw: bump_menu_cache(), sender=model, weak=False, dispatch_uid=f'menu_cache_del_{model.__name__}')
