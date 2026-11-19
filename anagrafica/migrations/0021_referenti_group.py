from django.db import migrations


def create_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Referenti")


class Migration(migrations.Migration):
    dependencies = [
        ("anagrafica", "0020_residente_estero"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [migrations.RunPython(create_group, migrations.RunPython.noop)]
