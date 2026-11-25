from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('api', '0007_brd_alignment')]
    operations = [
        migrations.AddField(model_name='table', name='qr_token', field=models.CharField(max_length=64, null=True, editable=False)),
    ]
