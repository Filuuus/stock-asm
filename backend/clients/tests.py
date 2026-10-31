from django.test import SimpleTestCase

from .services import PROPERTIES, client_email, client_values, format_phone, from_notion, plan_changes, to_notion

ROW = {
    'CIDCLIENTEPROVEEDOR': 7, 'CCODIGOCLIENTE': ' 103-001 ', 'CRAZONSOCIAL': 'RANCHO DE PRUEBA',
    'CEMAIL1': 'ventasgeasm@hotmail.com; rancho@example.com', 'CNOMBREAGENTE': 'ZONA 1',
    'CTELEFONO1': '(378) 712 34 56', 'CTELEFONO2': '378-712-3456', 'CMUNICIPIO': 'Acatic',
}


def notion_page(values):
    """What Notion sends back for a page written with to_notion(values)."""
    props = {}
    for name, prop in to_notion(values).items():
        kind = PROPERTIES[name]
        raw = prop[kind]
        if kind in ('title', 'rich_text'):
            raw = [{'plain_text': t['text']['content']} for t in raw]
        props[name] = {'type': kind, kind: raw}
    return {'properties': props}


class ClientValuesTests(SimpleTestCase):
    def test_phone_formats(self):
        self.assertEqual(format_phone('(378) 712 34 56'), '378 712 3456')
        self.assertEqual(format_phone('33-1388-3418'), '33 1388 3418')
        self.assertEqual(format_phone('+52 33 1388 3418'), '33 1388 3418')
        self.assertEqual(format_phone(' 99*99*99999 '), '99*99*99999')
        self.assertIsNone(format_phone('  '))

    def test_email_skips_company_addresses(self):
        self.assertEqual(client_email(ROW['CEMAIL1']), 'rancho@example.com')
        self.assertIsNone(client_email('atencionclientes_agrostma@hotmail.com'))
        self.assertIsNone(client_email(None))

    def test_values_drop_repeated_phone_and_blank_fields(self):
        values = client_values({**ROW, 'CMUNICIPIO': '  '}, None)
        self.assertEqual(values['Código'], '103-001')
        self.assertEqual(values['Teléfono'], '378 712 3456')
        self.assertIsNone(values['Teléfono 2'])
        self.assertIsNone(values['Municipio'])
        self.assertTrue(values['Activo'])

    def test_second_phone_moves_up_when_first_is_empty(self):
        values = client_values({**ROW, 'CTELEFONO1': '', 'CTELEFONO2': '3313883418'}, None)
        self.assertEqual((values['Teléfono'], values['Teléfono 2']), ('33 1388 3418', None))

    def test_notion_round_trip(self):
        values = client_values(ROW, 'https://www.google.com/maps?q=20.8,-102.9')
        self.assertEqual(from_notion(notion_page(values)), values)
        empty = {**values, 'Zona': None, 'Municipio': None, 'Email': None}
        self.assertEqual(from_notion(notion_page(empty)), empty)


class PlanChangesTests(SimpleTestCase):
    def test_creates_updates_and_deactivates(self):
        same = client_values(ROW, None)
        moved = client_values({**ROW, 'CIDCLIENTEPROVEEDOR': 8, 'CMUNICIPIO': 'Tepatitlán'}, None)
        new = client_values({**ROW, 'CIDCLIENTEPROVEEDOR': 9}, None)
        wanted = {7: same, 8: moved, 9: new}
        existing = {
            7: ('p7', same),
            8: ('p8', {**moved, 'Municipio': 'Acatic'}),
            5: ('p5', {**same, 'ID ERP': 5}),                   # stopped buying
            6: ('p6', {**same, 'ID ERP': 6, 'Activo': False}),  # already inactive
        }
        creates, updates = plan_changes(wanted, existing)
        self.assertEqual(creates, [new])
        self.assertEqual(sorted(updates), [('p5', {'Activo': False}), ('p8', {'Municipio': 'Tepatitlán'})])

    def test_inactive_client_coming_back_is_reactivated(self):
        values = client_values(ROW, None)
        _, updates = plan_changes({7: values}, {7: ('p7', {**values, 'Activo': False})})
        self.assertEqual(updates, [('p7', {'Activo': True})])
