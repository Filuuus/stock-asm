from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        from django.db.backends.signals import connection_created

        def set_erp_isolation_level(sender, connection, **kwargs):
            # The ERP is a live Contpaqi server used for real transactions
            # during business hours - a plain read can otherwise queue for
            # minutes behind a lock held by someone's open Contpaqi window.
            # READ UNCOMMITTED (SQL Server's NOLOCK-equivalent isolation
            # level) makes our reads never wait on those locks. This only
            # affects how OUR connection reads - it changes nothing on the
            # ERP itself. Trade-off: can occasionally read uncommitted/
            # dirty data mid-edit - acceptable here since every feature
            # reading the ERP is explicitly a draft/reporting view, not a
            # source of truth for writes.
            if connection.alias == 'erp':
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED')

        connection_created.connect(set_erp_isolation_level)
