from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('api', '0002_rename_image_menuitem_image_url'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='StaffCall',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('message', models.CharField(blank=True, max_length=255)),
            ('status', models.CharField(choices=[('pending', 'Chờ tiếp nhận'), ('accepted', 'Đang xử lý'), ('resolved', 'Đã hoàn thành')], default='pending', max_length=20)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('handled_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ('table', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='staff_calls', to='api.table')),
        ],
        options={'ordering': ['status', '-created_at']},
    )]
