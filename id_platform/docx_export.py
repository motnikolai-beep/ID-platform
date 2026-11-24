"""Export a checked template payload as a clearly marked DOCX draft."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def export_docx(payload, directory):
    try:
        from docx import Document
        from docx.shared import Cm, Pt
    except ImportError as error:
        raise RuntimeError('Установите python-docx: python -m pip install -r requirements-docx.txt') from error
    template = payload['template']
    result = payload['result']
    if (result['template_id'], result['template_version']) != (template['id'], template['version']):
        raise ValueError('Версия результата не совпадает с шаблоном')
    document = Document()
    section = document.sections[0]
    section.top_margin = section.bottom_margin = Cm(2)
    section.left_margin = Cm(3)
    section.right_margin = Cm(1.5)
    style = document.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(12)
    document.add_paragraph('ЧЕРНОВИК — НЕ ПОДПИСАН', style='Title')
    document.add_heading(template['title'], level=1)
    document.add_paragraph('Универсальная выгрузка полей. Не подтверждает соответствие нормативной форме или применимость требований.')
    document.add_paragraph('Шаблон: ' + template['id'] + ' | Версия: ' + template['version'] + ' | Статус: ' + template['status'])
    document.add_paragraph('Сформировано UTC: ' + datetime.now(timezone.utc).isoformat(timespec='seconds'))
    table = document.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    table.rows[0].cells[0].text = 'Поле'
    table.rows[0].cells[1].text = 'Значение'
    for field in template['fields']:
        value = result['values'].get(field['name'])
        empty = value is None or value == '' or value == [] or value == {}
        text = 'НЕ ЗАПОЛНЕНО' if empty else (json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value))
        cells = table.add_row().cells
        cells[0].text = field.get('label', field['name'])
        cells[1].text = text
    missing = result.get('missing', [])
    labels = {f['name']: f.get('label', f['name']) for f in template['fields']}
    document.add_heading('Проверка заполнения', level=2)
    document.add_paragraph('Не заполнены обязательные поля: ' + ', '.join(labels.get(name, name) for name in missing) if missing else 'Обязательные поля заполнены. Содержание требует проверки человеком.')
    document.add_paragraph('Экспорт не означает согласование, подписание или выпуск документа.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ('draft_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex + '.docx')
    with path.open('xb') as stream:
        try:
            document.save(stream)
        except Exception:
            stream.close()
            path.unlink(missing_ok=True)
            raise
    return path
