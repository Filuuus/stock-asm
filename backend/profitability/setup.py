"""Route-cost setup that management edits on the page: who and which vehicles go to each pool, and
fixed monthly amounts. Read as one document and saved whole (replace), since it's a handful of rows.
GPS units (IMEIs) stay out of it: they're set locally and kept on save."""
from decimal import Decimal, InvalidOperation

from django.db import connections, transaction

from .models import POOL_CHOICES, PoolEmployee, PoolMonthlyCost, PoolVehicle
from .services import PAYROLL_DATABASE

POOLS = {code for code, _ in POOL_CHOICES}
VEHICLE_FIELDS = ['name', 'pool', 'sheet_name', 'maintenance_account', 'uses_lp', 'km_per_liter', 'price_per_liter',
                  'annual_insurance']


def fetch_payroll_employees(extra_ids):
    """Active payroll employees plus any already in the setup: {id: {name, position, active}}. Names
    are read live, never stored (public repo)."""
    ids = list(extra_ids) or [0]
    with connections['erp'].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT e.idempleado, e.nombrelargo, p.descripcion, e.estadoempleado
            FROM {PAYROLL_DATABASE}.dbo.nom10001 e
            LEFT JOIN {PAYROLL_DATABASE}.dbo.nom10006 p ON p.idpuesto = e.idpuesto
            WHERE e.estadoempleado IN ('A', 'R') OR e.idempleado IN ({', '.join(['%s'] * len(ids))})
            """,
            ids,
        )
        # 'R' = rehired, still active (2026-10-06 check).
        return {
            eid: {'name': (name or '').strip(), 'position': (position or '').strip(), 'active': status in ('A', 'R')}
            for eid, name, position, status in cursor.fetchall()
        }


def _vehicle(v):
    return {
        'id': v.id, 'name': v.name, 'pool': v.pool, 'sheet_name': v.sheet_name,
        'maintenance_account': v.maintenance_account, 'uses_lp': v.uses_lp, 'has_gps': bool(v.gps_imei),
        'km_per_liter': float(v.km_per_liter) if v.km_per_liter is not None else None,
        'price_per_liter': float(v.price_per_liter) if v.price_per_liter is not None else None,
        'annual_insurance': float(v.annual_insurance),
    }


def route_setup():
    employees = dict(PoolEmployee.objects.values_list('employee_id', 'pool'))
    people = fetch_payroll_employees(employees)
    return {
        'pools': [{'code': code, 'label': label} for code, label in POOL_CHOICES],
        'employees': [{'employee_id': eid, 'pool': pool, **people.get(eid, {'name': '', 'position': '', 'active': False})}
                      for eid, pool in employees.items()],
        'employee_options': sorted(
            ({'employee_id': eid, **p} for eid, p in people.items() if p['active']), key=lambda p: p['name']),
        'vehicles': [_vehicle(v) for v in PoolVehicle.objects.order_by('pool', 'name')],
        'monthly_costs': [{'id': c.id, 'label': c.label, 'pool': c.pool, 'monthly_amount': float(c.monthly_amount)}
                          for c in PoolMonthlyCost.objects.order_by('pool', 'label')],
    }


def _amount(value, field, allow_none=False):
    if value in (None, '') and allow_none:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{field}: debe ser un número.')
    if number < 0:
        raise ValueError(f'{field}: no puede ser negativo.')
    return number


def save_route_setup(data):
    """Replaces the setup with `data` (same shape as route_setup). Raises ValueError with a message
    for the user on bad input; nothing is saved then."""
    employees, vehicles, costs = [], [], []
    for e in data.get('employees', []):
        if e.get('pool') not in POOLS:
            raise ValueError('Cada empleado necesita un grupo válido.')
        employees.append(PoolEmployee(employee_id=int(e['employee_id']), pool=e['pool']))
    if len({e.employee_id for e in employees}) != len(employees):
        raise ValueError('Un empleado aparece dos veces.')
    for v in data.get('vehicles', []):
        name = (v.get('name') or '').strip()
        if not name or v.get('pool') not in POOLS:
            raise ValueError('Cada vehículo necesita nombre y grupo.')
        vehicles.append({
            'id': v.get('id'), 'name': name, 'pool': v['pool'],
            'sheet_name': (v.get('sheet_name') or '').replace(' ', '').upper(),
            'maintenance_account': (v.get('maintenance_account') or '').strip(), 'uses_lp': bool(v.get('uses_lp')),
            'km_per_liter': _amount(v.get('km_per_liter'), f'{name}: km por litro', True),
            'price_per_liter': _amount(v.get('price_per_liter'), f'{name}: precio por litro', True),
            'annual_insurance': _amount(v.get('annual_insurance') or 0, f'{name}: seguro anual'),
        })
    for c in data.get('monthly_costs', []):
        label = (c.get('label') or '').strip()
        if not label or c.get('pool') not in POOLS:
            raise ValueError('Cada gasto fijo necesita concepto y grupo.')
        costs.append(PoolMonthlyCost(label=label, pool=c['pool'],
                                     monthly_amount=_amount(c.get('monthly_amount'), f'{label}: monto mensual')))

    with transaction.atomic():
        PoolEmployee.objects.all().delete()
        PoolEmployee.objects.bulk_create(employees)
        keep = {v['id'] for v in vehicles if v['id']}
        PoolVehicle.objects.exclude(id__in=keep).delete()
        for v in vehicles:
            fields = {k: v[k] for k in VEHICLE_FIELDS}
            if v['id']:
                PoolVehicle.objects.filter(id=v['id']).update(**fields)  # keeps its GPS unit
            else:
                PoolVehicle.objects.create(**fields)
        PoolMonthlyCost.objects.all().delete()
        PoolMonthlyCost.objects.bulk_create(costs)
