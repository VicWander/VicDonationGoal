"""Build both local manual pages without third-party packages.

Supports the Markdown forms used by MANUAL.md. --check verifies generated
copies and all local anchors without changing any files.
"""
import argparse
import html
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parent / 'core' / 'public' / 'docs'


def inline(text):
    parts = re.split(r'(`[^`]+`)', text)
    for i, part in enumerate(parts):
        if part.startswith('`') and part.endswith('`'):
            parts[i] = '<code>' + html.escape(part[1:-1]) + '</code>'
        else:
            part = html.escape(part)
            part = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', part)
            part = re.sub(r'\[([^]]+)\]\((https?://[^)]+|#[^)]+)\)', r'<a href="\2">\1</a>', part)
            parts[i] = part
    return ''.join(parts)


def render(source):
    lines = source.splitlines()
    body, headings, used = [], [], Counter()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith('```'):
            lang, content = line[3:], []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                content.append(lines[i])
                i += 1
            if i == len(lines):
                raise ValueError('Unclosed code fence')
            body.append('<pre><code class="language-' + html.escape(lang) + '">' + html.escape('\n'.join(content)) + '</code></pre>')
        elif re.match(r'#{1,4} ', line):
            level = len(line.split(' ', 1)[0])
            title = line[level + 1:]
            explicit=re.search(r' \{#([a-z0-9-]+)\}$',title)
            if explicit:title=title[:explicit.start()]
            slug = explicit.group(1) if explicit else re.sub(r'[^\w\s-]', '', title.lower())
            slug = re.sub(r'\s+', '-', slug)
            used[slug] += 1
            anchor = slug + (f'-{used[slug]}' if used[slug] > 1 else '')
            headings.append((level, title, anchor))
            body.append(f'<h{level} id="{anchor}">{inline(title)}<a class="heading-anchor" href="#{anchor}" aria-label="Ссылка на раздел {html.escape(title, quote=True)}">#</a></h{level}>')
        elif line == '---':
            body.append('<hr>')
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                row = lines[i].strip().strip('|').split('|')
                if not all(re.fullmatch(r'\s*:?-+:?\s*', cell) for cell in row):
                    tag = 'th' if not rows else 'td'
                    rows.append('<tr>' + ''.join(f'<{tag}>{inline(cell.strip())}</{tag}>' for cell in row) + '</tr>')
                i += 1
            body.append('<div class="table-scroll" tabindex="0" aria-label="Таблица"><table><thead>' + rows[0] + '</thead><tbody>' + ''.join(rows[1:]) + '</tbody></table></div>')
            continue
        elif re.match(r'(?:- |\d+\. )', line):
            ordered = line[0].isdigit()
            pattern = r'\d+\. ' if ordered else r'- '
            tag = 'ol' if ordered else 'ul'
            items = []
            while i < len(lines) and re.match(pattern, lines[i].strip()):
                items.append('<li>' + inline(re.sub('^' + pattern, '', lines[i].strip())) + '</li>')
                i += 1
            body.append(f'<{tag}>' + ''.join(items) + f'</{tag}>')
            continue
        else:
            content = [line]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r'^(?:#{1,4} |```|\||- |\d+\. |---$)', lines[i + 1].strip()):
                i += 1
                content.append(lines[i].strip())
            body.append('<p>' + inline(' '.join(content)) + '</p>')
        i += 1
    nav = []
    for level, title, anchor in headings:
        if level <= 2:
            nav.append(f'<a class="level-{level}" href="#{anchor}">{html.escape(title)}</a>')
    return '\n'.join(body), '\n'.join(nav)


def page():
    body, nav = render((ROOT / 'MANUAL.md').read_text(encoding='utf-8-sig'))
    return f'''<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><meta name="description" content="Техническая справка VicDonationGoal 1.5: параметры виджета, подключения, TTS, данные и API."><title>Справка 1.5 — VicDonationGoal</title><link rel="stylesheet" href="docs-theme.css"></head>
<body data-theme-no-migrate><a class="skip-link" href="#manual">К содержимому</a>
<div class="layout"><aside class="sidebar"><a class="brand" href="https://vicwander.github.io/VicDonationGoal/">VicDonationGoal<span>Техническая справка · 1.5</span></a>
<label class="search-label" for="docSearch">Поиск в справочнике</label><input id="docSearch" name="q" type="search" placeholder="Параметр, сервис, ошибка…" autocomplete="off"><div id="docSearchResults" hidden></div>
<nav class="nav" aria-label="Содержание справочника">{nav}</nav><div id="sidebarThemeSlot"></div><a class="back-link" href="https://github.com/VicWander/VicDonationGoal">GitHub проекта</a><a class="back-link local-admin" hidden href="/admin.html">Открыть админку</a></aside>
<main class="content" id="manual"><div class="doc-meta"><span>Версия 1.5</span><span>Справочник параметров и поведения</span></div>{body}<footer>VicDonationGoal 1.5 · Практические уроки доступны в Гайдбуке приложения.</footer></main></div><script src="docs-theme.js"></script></body></html>'''


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a' and attrs.get('href', '').startswith('#'):
            self.links.append(attrs['href'][1:])


def validate(text):
    parser = Anchors()
    parser.feed(text)
    assert len(parser.ids) == len(set(parser.ids)), 'Duplicate anchors'
    assert set(parser.links) <= set(parser.ids), 'Broken anchors: ' + str(set(parser.links) - set(parser.ids))
    assert 'v1.4.4 — Руководство' not in text
    assert 'data-theme-no-migrate' in text
    assert text.count('<pre>') == text.count('</pre>')
    return len(parser.ids), len(parser.links)


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--check', action='store_true')
    check = args.parse_args().check
    text = page()
    counts = validate(text)
    for folder in (ROOT, PUBLIC):
        target = folder / 'index.html'
        if check:
            assert target.read_text(encoding='utf-8') == text, f'Stale HTML: {target}'
        else:
            target.write_text(text, encoding='utf-8')
    for name in ('docs-theme.css', 'docs-theme.js'):
        source = (ROOT / name).read_bytes()
        if check:
            assert source == (PUBLIC / name).read_bytes(), f'Stale asset: {name}'
        else:
            (PUBLIC / name).write_bytes(source)
    print(f'Manual {"verified" if check else "built"}: two matching copies, {counts[0]} unique anchors, {counts[1]} valid internal links.')


if __name__ == '__main__':
    main()
