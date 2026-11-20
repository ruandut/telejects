from django.db import migrations


def make_book(apps, schema_editor):
    PriceBook = apps.get_model("pricebook", "PriceBook")
    PriceBook.objects.get_or_create(name="Telejects", defaults={"available_to_all": True})


class Migration(migrations.Migration):
    dependencies = [("pricebook", "0001_initial")]

    operations = [migrations.RunPython(make_book, migrations.RunPython.noop)]
