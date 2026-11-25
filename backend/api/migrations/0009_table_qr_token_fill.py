import secrets

from django.db import migrations


def fill_tokens(apps, schema_editor):
    Table = apps.get_model('api', 'Table')
    for table in Table.objects.filter(qr_token__isnull=True):
        table.qr_token = secrets.token_urlsafe(24)
        table.save(update_fields=['qr_token'])


class Migration(migrations.Migration):
    dependencies = [('api', '0008_table_qr_token_add')]
    operations = [migrations.RunPython(fill_tokens, migrations.RunPython.noop)]
