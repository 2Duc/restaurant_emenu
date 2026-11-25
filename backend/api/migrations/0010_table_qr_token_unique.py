from django.db import migrations, models

import api.models


class Migration(migrations.Migration):
    dependencies = [('api', '0009_table_qr_token_fill')]
    operations = [
        migrations.AlterField(model_name='table', name='qr_token',
                              field=models.CharField(default=api.models.new_qr_token, editable=False, max_length=64, unique=True)),
    ]
