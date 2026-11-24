"""New template UI; original SKRF.py remains unchanged."""
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
import flet as ft
from id_platform.templates import load_catalog, prefill, TemplateError

ROOT = Path(__file__).resolve().parent


def context_from(values):
    result = {}
    for source, value in values.items():
        parts = source.split('.')
        if not all(parts):
            raise ValueError('Некорректный путь поля: ' + source)
        node = result
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ValueError('Конфликт путей: ' + source)
        if isinstance(node.get(parts[-1]), dict):
            raise ValueError('Конфликт путей: ' + source)
        node[parts[-1]] = value
    return result


def main(page):
    page.title = 'ID-platform | Шаблоны'
    page.theme_mode = ft.ThemeMode.DARK
    folder = Path(os.environ.get('ID_PLATFORM_DATA_DIR') or Path.home() / '.id-platform')
    folder.mkdir(parents=True, exist_ok=True)
    database = folder / 'platform.db'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, created TEXT NOT NULL, title TEXT NOT NULL, payload TEXT NOT NULL)')
    state = {'selected': None, 'values': {}}
    title = ft.TextField(label='Объект')
    notice = ft.Text('Изменения сохраняются только кнопкой сохранения.')
    drafts = ft.Checkbox(label='Показать непроверенные формы', value=False)
    catalog, fields, preview, history = (ft.Column() for _ in range(4))
    editors = {}

    def capture():
        state['values']['project.title'] = (title.value or '').strip()
        for source, control in editors.items():
            state['values'][source] = (control.value or '').strip()

    def invalidate(event=None):
        preview.controls.clear()
        page.update()

    def safe(action):
        def handler(event):
            try:
                action()
            except (OSError, ValueError, sqlite3.Error) as error:
                notice.value = 'Ошибка: ' + str(error)
            page.update()
        return handler

    def choose(template):
        capture()
        state['selected'] = template
        editors.clear()
        fields.controls.clear()
        preview.controls.clear()
        fields.controls.append(ft.Text(template['title'] + ' | ' + template['version'] + ' | ' + template['status']))
        for field in template['fields']:
            source = field['source']
            if source == 'project.title' or source in editors:
                continue
            control = ft.TextField(label=field.get('label', field['name']), value=str(state['values'].get(source, '')), on_change=invalidate)
            editors[source] = control
            fields.controls.append(control)

    def reload_catalog():
        capture()
        state['selected'] = None
        editors.clear()
        fields.controls.clear()
        preview.controls.clear()
        catalog.controls.clear()
        templates = load_catalog(ROOT / 'catalog' / 'templates', bool(drafts.value))
        for template in templates:
            catalog.controls.append(ft.TextButton(template['title'] + ' | ' + template['version'], on_click=safe(lambda t=template: choose(t))))
        notice.value = 'Форм: ' + str(len(templates)) + '. Учебные формы видны при включении непроверенных.'

    def check():
        capture()
        template = state['selected']
        if template is None:
            raise ValueError('Выберите форму')
        data = prefill(template, context_from(state['values']))
        preview.controls.clear()
        for field in template['fields']:
            name = field['name']
            value = data['values'][name]
            preview.controls.append(ft.Text(field.get('label', name) + ': ' + str(value if value is not None else 'НЕ ЗАПОЛНЕНО')))
            preview.controls.append(ft.Text('Источник: ' + data['provenance'].get(name, 'нет данных'), size=11))
        preview.controls.append(ft.Text('Не заполнено: ' + ', '.join(data['missing']) if data['missing'] else 'Обязательные поля заполнены. Проверьте содержание.'))
        preview.controls.append(ft.Text('Только черновик данных. Применимость и подпись не проверены.'))
        return {'template': template, 'values': dict(state['values']), 'result': data}

    def show_history():
        history.controls.clear()
        with sqlite3.connect(database) as db:
            rows = db.execute('SELECT created, title, payload FROM snapshots ORDER BY created DESC').fetchall()
        for created, name, payload in rows:
            history.controls.append(ft.Text(created + ' | ' + name))
            history.controls.append(ft.Text(json.dumps(json.loads(payload)['result']['values'], ensure_ascii=False, indent=2), selectable=True))

    def save():
        payload = check()
        name = (title.value or '').strip()
        if not name:
            raise ValueError('Введите название объекта')
        with sqlite3.connect(database) as db:
            db.execute('INSERT INTO snapshots VALUES (?, ?, ?, ?)', (str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(), name, json.dumps(payload, ensure_ascii=False)))
        show_history()
        notice.value = 'Снимок проекта и черновик сохранены'

    title.on_change = invalidate
    drafts.on_change = safe(reload_catalog)
    page.add(ft.Column([
        ft.Text('ID-platform — шаблоны документов', size=24),
        ft.Text('Новая версия. Оригинальный SKRF.py не изменён. Данные вводятся как текст.'),
        notice, title, drafts,
        ft.TextButton('Обновить каталог', on_click=safe(reload_catalog)), catalog, fields,
        ft.TextButton('Предзаполнить и проверить', on_click=safe(check)),
        ft.TextButton('Сохранить снимок проекта и черновик', on_click=safe(save)),
        preview, ft.Divider(), ft.Text('Сохранённые снимки всех объектов'), history,
    ], expand=True, scroll=ft.ScrollMode.AUTO))
    try:
        show_history()
        reload_catalog()
    except (OSError, ValueError, sqlite3.Error) as error:
        notice.value = 'Ошибка загрузки: ' + str(error)
    page.update()


if __name__ == '__main__':
    ft.run(main)
