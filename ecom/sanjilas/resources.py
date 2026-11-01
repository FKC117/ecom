from import_export import resources
from .models import SiteSettings, HomePage


class SiteSettingsResource(resources.ModelResource):
    class Meta:
        model = SiteSettings
        import_id_fields = ("id",)
        exclude = ("updated_at",)
        clean_model_instances = True
        use_transactions = True

    def before_import_row(self, row, **kwargs):
        if str(row.get("id", "1")).strip() not in {"", "1"}:
            raise ValueError("Site settings must use ID 1.")
        row["id"] = 1


class HomePageResource(SiteSettingsResource):
    class Meta:
        model = HomePage
        import_id_fields = ("id",)
        clean_model_instances = True
        use_transactions = True
