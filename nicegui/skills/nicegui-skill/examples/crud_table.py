#!/usr/bin/env python3
"""
NiceGUI CRUD Table Template
----------------------------
Demonstrates: ag-grid editing, add/edit/delete dialogs, search/filter,
@ui.refreshable, form validation, confirm dialogs.
Run: python crud_table.py
"""
import uuid
from dataclasses import dataclass, field, asdict

from nicegui import ui

# ─── Data model ──────────────────────────────────────────────────────────────

@dataclass
class Person:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ''
    email: str = ''
    department: str = 'Engineering'
    role: str = 'Engineer'
    status: str = 'active'


DEPARTMENTS = ['Engineering', 'Product', 'Design', 'Marketing', 'Sales', 'HR']
ROLES = ['Engineer', 'Manager', 'Lead', 'Director', 'Intern']
STATUSES = ['active', 'inactive', 'pending']

# Sample data
db: list[Person] = [
    Person(name='Alice Johnson', email='alice@company.com', department='Engineering', role='Lead', status='active'),
    Person(name='Bob Smith',     email='bob@company.com',   department='Product',     role='Manager', status='active'),
    Person(name='Carol White',   email='carol@company.com', department='Design',      role='Engineer', status='inactive'),
    Person(name='David Lee',     email='david@company.com', department='Engineering', role='Intern', status='pending'),
    Person(name='Eve Davis',     email='eve@company.com',   department='Marketing',   role='Director', status='active'),
]

# Filter state
filter_state = {
    'query': '',
    'department': 'All',
    'status': 'All',
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def filtered_people() -> list[Person]:
    q = filter_state['query'].lower()
    dept = filter_state['department']
    status = filter_state['status']
    return [
        p for p in db
        if (not q or q in p.name.lower() or q in p.email.lower())
        and (dept == 'All' or p.department == dept)
        and (status == 'All' or p.status == status)
    ]


def find_person(person_id: str) -> Person | None:
    return next((p for p in db if p.id == person_id), None)


STATUS_COLORS = {'active': 'positive', 'inactive': 'grey', 'pending': 'warning'}


# ─── Person form (shared by Add & Edit) ──────────────────────────────────────

def person_form(person: Person) -> dict[str, ui.element]:
    """Renders form fields and returns references for reading values."""
    name_inp   = ui.input('Full Name', value=person.name).classes('w-full')
    email_inp  = ui.input('Email', value=person.email).props('type=email').classes('w-full')
    dept_inp   = ui.select(DEPARTMENTS, label='Department', value=person.department).classes('w-full')
    role_inp   = ui.select(ROLES, label='Role', value=person.role).classes('w-full')
    status_inp = ui.toggle(STATUSES, value=person.status).classes('mt-1')

    return {'name': name_inp, 'email': email_inp, 'department': dept_inp, 'role': role_inp, 'status': status_inp}


def validate_form(fields: dict) -> str | None:
    """Returns error message or None if valid."""
    if not fields['name'].value.strip():
        return 'Name is required'
    if not fields['email'].value.strip() or '@' not in fields['email'].value:
        return 'Valid email is required'
    return None


# ─── Main table view ─────────────────────────────────────────────────────────

@ui.refreshable
def people_table():
    people = filtered_people()

    columns = [
        {'name': 'name',       'label': 'Name',       'field': 'name',       'sortable': True, 'align': 'left'},
        {'name': 'email',      'label': 'Email',      'field': 'email',      'sortable': True, 'align': 'left'},
        {'name': 'department', 'label': 'Department', 'field': 'department', 'sortable': True, 'align': 'left'},
        {'name': 'role',       'label': 'Role',       'field': 'role',       'sortable': True, 'align': 'left'},
        {'name': 'status',     'label': 'Status',     'field': 'status',     'sortable': True, 'align': 'left'},
        {'name': 'actions',    'label': 'Actions',    'field': 'id',                           'align': 'right'},
    ]
    rows = [asdict(p) for p in people]

    with ui.table(columns=columns, rows=rows, row_key='id', pagination=10).classes('w-full') as table:
        # Search in top-right
        with table.add_slot('top-right'):
            ui.input(placeholder='Search name/email...').props('dense clearable outlined') \
                .classes('w-48') \
                .on_value_change(lambda e: [filter_state.update({'query': e.value}), people_table.refresh()])

        # Custom body for status badge + action buttons
        with table.add_slot('body'):
            with ui.tr(props='key=row.id'):
                ui.td('{{ row.name }}')
                ui.td('{{ row.email }}').classes('text-grey-6 text-sm')
                ui.td('{{ row.department }}')
                ui.td('{{ row.role }}')
                with ui.td():
                    ui.badge(
                        '{{ row.status }}',
                        color='positive',  # overridden by v-bind below
                    ).props(":color=\"{active:'positive',inactive:'grey',pending:'warning'}[row.status]\"")
                with ui.td():
                    with ui.row().classes('gap-1 justify-end'):
                        ui.button(icon='edit', on_click=lambda row=None: None) \
                            .props('flat round dense size=sm') \
                            .on('click', lambda e: open_edit_dialog(e.args.get('row_id')))
                        ui.button(icon='delete') \
                            .props('flat round dense size=sm color=negative') \
                            .on('click', lambda e: open_delete_dialog(e.args.get('row_id')))

    if not people:
        with ui.column().classes('w-full items-center py-12 gap-3'):
            ui.icon('search_off', size='3rem').classes('text-grey-4')
            ui.label('No people found').classes('text-xl text-grey-5')
            ui.label('Try adjusting your filters').classes('text-sm text-grey-4')


# ─── Dialogs ─────────────────────────────────────────────────────────────────

async def open_add_dialog():
    new_person = Person()

    with ui.dialog().classes('w-full') as dialog, ui.card().classes('w-full max-w-lg p-6'):
        ui.label('Add Person').classes('text-xl font-semibold mb-4')
        fields = person_form(new_person)
        error_lbl = ui.label('').classes('text-red-500 text-sm').set_visibility(False)

        def save():
            err = validate_form(fields)
            if err:
                error_lbl.text = err
                error_lbl.set_visibility(True)
                return
            new_person.name       = fields['name'].value
            new_person.email      = fields['email'].value
            new_person.department = fields['department'].value
            new_person.role       = fields['role'].value
            new_person.status     = fields['status'].value
            db.append(new_person)
            people_table.refresh()
            update_stats()
            dialog.close()
            ui.notify(f'Added {new_person.name}', type='positive')

        with ui.row().classes('w-full justify-end gap-2 mt-6'):
            ui.button('Cancel', on_click=dialog.close).props('flat no-caps')
            ui.button('Add Person', icon='add', on_click=save).props('color=primary no-caps')

    await dialog


async def open_edit_dialog(person_id: str):
    person = find_person(person_id)
    if not person:
        return

    with ui.dialog() as dialog, ui.card().classes('w-full max-w-lg p-6'):
        ui.label(f'Edit {person.name}').classes('text-xl font-semibold mb-4')
        fields = person_form(person)
        error_lbl = ui.label('').classes('text-red-500 text-sm').set_visibility(False)

        def save():
            err = validate_form(fields)
            if err:
                error_lbl.text = err
                error_lbl.set_visibility(True)
                return
            person.name       = fields['name'].value
            person.email      = fields['email'].value
            person.department = fields['department'].value
            person.role       = fields['role'].value
            person.status     = fields['status'].value
            people_table.refresh()
            update_stats()
            dialog.close()
            ui.notify(f'Updated {person.name}', type='positive')

        with ui.row().classes('w-full justify-end gap-2 mt-6'):
            ui.button('Cancel', on_click=dialog.close).props('flat no-caps')
            ui.button('Save Changes', icon='save', on_click=save).props('color=primary no-caps')

    await dialog


async def open_delete_dialog(person_id: str):
    person = find_person(person_id)
    if not person:
        return

    with ui.dialog() as dialog, ui.card().classes('w-80 p-6'):
        ui.label('Delete Person').classes('text-xl font-semibold')
        ui.label(f'Are you sure you want to delete {person.name}?').classes('text-grey-6 mt-2')
        ui.label('This action cannot be undone.').classes('text-sm text-red-500')

        with ui.row().classes('w-full justify-end gap-2 mt-6'):
            ui.button('Cancel', on_click=lambda: dialog.submit(False)).props('flat no-caps')
            ui.button('Delete', icon='delete', on_click=lambda: dialog.submit(True)).props('color=negative no-caps')

    result = await dialog
    if result:
        db.remove(person)
        people_table.refresh()
        update_stats()
        ui.notify(f'Deleted {person.name}', type='positive')


# ─── Stats bar ───────────────────────────────────────────────────────────────

stats_labels: dict[str, ui.label] = {}

def update_stats():
    total  = len(db)
    active = sum(1 for p in db if p.status == 'active')
    for key, val in [('total', total), ('active', active), ('inactive', total - active)]:
        if key in stats_labels:
            stats_labels[key].text = str(val)


# ─── App ─────────────────────────────────────────────────────────────────────

@ui.page('/')
def index():
    with ui.header(elevated=True).classes('bg-primary text-white items-center px-6 h-14'):
        ui.label('People Manager').classes('text-xl font-bold')

    with ui.column().classes('w-full max-w-6xl mx-auto px-6 py-6 gap-4'):
        # Header row
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('People').classes('text-2xl font-bold')
            ui.button('Add Person', icon='add', on_click=open_add_dialog).props('color=primary no-caps')

        # Stats row
        with ui.row().classes('gap-4'):
            for key, label, color in [
                ('total',    'Total',    'text-grey-8'),
                ('active',   'Active',   'text-green-600'),
                ('inactive', 'Inactive', 'text-grey-5'),
            ]:
                with ui.card().classes('px-4 py-2'):
                    with ui.row().classes('items-baseline gap-1'):
                        stats_labels[key] = ui.label(str(len(db) if key == 'total' else sum(1 for p in db if p.status == key))).classes(f'text-xl font-bold {color}')
                        ui.label(label).classes('text-sm text-grey-5')

        # Filters
        with ui.row().classes('gap-3 items-center flex-wrap'):
            ui.label('Filter:').classes('text-sm text-grey-6')
            ui.select(
                ['All'] + DEPARTMENTS,
                value='All',
                label='Department',
            ).classes('w-40').props('dense outlined') \
             .on_value_change(lambda e: [filter_state.update({'department': e.value}), people_table.refresh()])

            ui.select(
                ['All'] + STATUSES,
                value='All',
                label='Status',
            ).classes('w-32').props('dense outlined') \
             .on_value_change(lambda e: [filter_state.update({'status': e.value}), people_table.refresh()])

            ui.button(
                'Clear Filters',
                icon='filter_alt_off',
                on_click=lambda: [
                    filter_state.update({'query': '', 'department': 'All', 'status': 'All'}),
                    people_table.refresh()
                ]
            ).props('flat no-caps dense')

        # Table
        people_table()


ui.run(title='CRUD Table', port=8082, reload=True)
