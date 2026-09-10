class ERPRouter:
    """Routes the two Contpaqi ERP tables to the read-only 'erp' connection.
    Everything else (ProductImage, auth, sessions, ...) stays on 'default'.
    """

    erp_models = {"admproductos", "admexistenciacosto"}

    def db_for_read(self, model, **hints):
        if model._meta.app_label == "api" and model._meta.model_name in self.erp_models:
            return "erp"
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == "api" and model._meta.model_name in self.erp_models:
            return "erp"
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == "erp":
            return False
        if model_name in self.erp_models:
            return False
        return None
