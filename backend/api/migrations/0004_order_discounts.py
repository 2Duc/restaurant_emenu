from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('api', '0003_staffcall')]
    operations = [
        migrations.AddField(model_name='order', name='subtotal_amount', field=models.DecimalField(decimal_places=0, default=0, max_digits=14)),
        migrations.AddField(model_name='order', name='discount_amount', field=models.DecimalField(decimal_places=0, default=0, max_digits=14)),
        migrations.AddField(model_name='order', name='promotion', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to='api.promotion')),
        migrations.RunPython(lambda apps, schema: apps.get_model('api','Order').objects.filter(subtotal_amount=0).update(subtotal_amount=models.F('total_amount')), migrations.RunPython.noop),
    ]
