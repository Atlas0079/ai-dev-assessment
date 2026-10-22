"""One report view for the HR page and the downloadable PDF."""
from html import escape
import json
import os
from pathlib import Path
from string import Template
import threading

from .hr_jobs import OWNERS, STATES
from .report import report_facts
from .storage import load

_pdf_lock = threading.Lock()
TEMPLATES = Path(__file__).with_name('templates')


def clipped(value, limit=1800):
    text = str(value)
    return text if len(text) <= limit else text[:limit] + '…（已截短，完整内容见原始证据）'


def report_view(store, job):
    facts = report_facts(store.results(job), job['tasks'])
    view = dict(title='候选人评测报告', state=job['state'], identity=[
        ['候选人', job['candidateId']], ['提交版本', str(job['submissionVersion'] or '未识别')],
        ['题包版本', job['releaseVersion']], ['处理状态', STATES[job['state']]],
        ['更新时间（UTC）', job['updatedAt']], ['记录编号', job['id']],
        ['执行轮次', str(job['attempt'])], ['答案 SHA-256', job['sha256']]],
        issues=[], tasks=[], unsubmitted=facts['unsubmitted'] if job['tasks'] else [],
        subjective={'status': '未启用', 'suggestions': []})
    if 'environmentVersion' in job:
        view['identity'].append(['固定环境', job['environmentVersion']])
    for item in job['issues']:
        view['issues'].append({**item, 'ownerLabel': OWNERS[item['owner']],
                               'faultId': job['id'] if item['owner'] in {'platform', 'undetermined'} else None})
    for fact in facts['tasks']:
        task, result = fact['id'], fact['result']
        row = dict(id=task, title=fact['title'], identity=[], groups=[], notAssessed=[], notes=list(fact['notes']))
        if result['status'] == 'NOT_RUN':
            row['notes'] = ['未执行。' + ' '.join(i['message'] for i in job['issues'] if i['task'] in {None, task})]
        else:
            row['identity'] = [['检查器版本', result['checkVersion']], ['检查时间（UTC）', result['evaluatedAt']]]
            execution = result['execution']
            for key, label in [('mode', '执行方式'), ('storage', '存储'), ('modelMode', '模型验证方式'), ('environmentVersion', '固定环境')]:
                if key in execution:
                    row['identity'].append([label, str(execution[key])])
            for group in fact['groups']:
                state, title = group['state'], group['title']
                cases = []
                for case in group['cases']:
                    evidences = []
                    for eid in case['evidenceIds']:
                        evidences.append(dict(id=eid, url=f'/api/jobs/{job["id"]}/evidence/{task}/{eid}.json?attempt={job["attempt"]}'))
                    summary = None
                    if evidences and state != 'PASS':
                        folder = store._folder(job['id']) / job['results'][task]
                        path = folder.parent / 'evidence' / (evidences[-1]['id'] + '.json')
                        if path.is_file():
                            event = load(path)
                            summary = clipped(json.dumps({k: event[k] for k in
                                ('method', 'path', 'request', 'status', 'response', 'transportError') if k in event},
                                ensure_ascii=False), 900)
                    cases.append(dict(id=case['id'], title=case['title'], detail=clipped(case['detail']),
                                      evidence=evidences, evidenceSummary=summary))
                if cases:
                    row['groups'].append(dict(state=state, title=title, cases=cases))
            row['notAssessed'] = result['notAssessed']
        view['tasks'].append(row)
    return view


def html_report(view):
    """Render escaped report facts into a self-contained, script-free document."""
    identity = dict(view['identity'])
    counts = {state: sum(len(group['cases']) for task in view['tasks']
                        for group in task['groups'] if group['state'] == state)
              for state in ('PASS', 'FAIL', 'NOT_RUN', 'ERROR')}
    labels = {'PASS': '已通过', 'FAIL': '未通过', 'NOT_RUN': '未完成', 'ERROR': '检查异常'}
    tone = {'PASS': 'pass', 'FAIL': 'fail', 'NOT_RUN': 'pending', 'ERROR': 'error'}
    def e(value):
        return escape(str(value), quote=True)
    def badge(label, style='neutral'):
        return f'<span class="badge {style}">{e(label)}</span>'
    def heading(title, extra=''):
        return f'<div class="section-title"><h2>{e(title)}</h2>{extra}</div>'
    total = sum(counts.values())
    state = view['state']
    state_tone = ('pending' if state in {'PLATFORM_BLOCKED', 'REVIEW_REQUIRED', 'NEEDS_ACTION'} else
                  'fail' if counts['FAIL'] else 'neutral')
    state_label = STATES[state]
    if state == 'COMPLETED' and counts['FAIL']:
        state_label += '，有未通过项'
    if state == 'COMPLETED' and counts['ERROR']:
        state_tone = 'error'
    overview = []
    if total:
        overview.append('<div class="metrics">')
        for status, number in counts.items():
            overview.append(f'<div class="metric {tone[status]}{" zero" if not number else ""}"><span>{labels[status]}</span>'
                            f'<strong>{number}</strong><small>项</small></div>')
        overview.append('</div>')
    else:
        overview.append('<div class="empty-result"><strong>尚未产生用例结果</strong>'
                        '<span>本报告记录当前处理情况。</span></div>')
    tasks = []
    for task in view['tasks']:
        numbers = {status: sum(len(group['cases']) for group in task['groups'] if group['state'] == status)
                   for status in counts}
        task_state = '已执行检查' if sum(numbers.values()) else '未执行'
        tasks.append(f'<tr><td><strong>{e(task["id"])}</strong><span class="table-subtitle">{e(task["title"])}</span></td>'
                     f'<td>{badge(task_state, "neutral" if sum(numbers.values()) else "pending")}</td>' +
                     ''.join(f'<td class="number {tone[status]}{" zero" if not number else ""}">{number if sum(numbers.values()) else "-"}</td>'
                             for status, number in numbers.items()) + '</tr>')
    if tasks:
        overview.append('<table class="task-table"><thead><tr><th>已选题目</th><th>执行情况</th>'
                        '<th>通过</th><th>未通过</th><th>未完成</th><th>异常</th></tr></thead><tbody>' +
                        ''.join(tasks) + '</tbody></table>')
    else:
        overview.append('<p class="muted">题目尚未识别。</p>')
    if view['unsubmitted']:
        overview.append('<p class="scope-line">未选做：' + '、'.join(e(t) for t in view['unsubmitted']) + '</p>')
    notices = []
    for task in view['tasks']:
        for note in task['notes']:
            # Unexecuted explanations are in the task/issue sections. Validation
            # object and model-mode qualifications must stay prominent.
            if task['groups'] or not any(i['task'] in {None, task['id']} for i in view['issues']):
                notices.append(f'<p class="notice">{e(task["id"])}：{e(note)}</p>')
    overview.extend(notices)

    attention = []
    for item in view['issues']:
        title = (item['task'] + '：' if item['task'] else '') + item['message']
        attention.append('<article class="issue-card">' +
            f'<div class="card-heading">{badge(item["ownerLabel"], "pending")}<h3>{e(title)}</h3></div>'
            f'<p class="action"><span>下一步</span>{e(item["action"])}</p>'
            f'<p class="fine">阶段：{e(item["stage"])}' +
            (f' · 受影响用例：{e("、".join(item["cases"]))}' if item['cases'] else '') + '</p>' +
            (f'<p class="fine">故障编号：<span class="mono">{e(item["faultId"])}</span></p>' if item['faultId'] else '') +
            '</article>')
    evidence_rows = []
    checks = []
    for task in view['tasks']:
        for group in task['groups']:
            if group['state'] == 'PASS':
                continue
            for case in group['cases']:
                reference = ''
                if case['evidence']:
                    number = len(evidence_rows) + 1
                    anchor = f'evidence-{number}'
                    reference = f'<a class="evidence-ref" href="#{anchor}">证据 E{number} · 见附录</a>'
                    summary = case['evidenceSummary']
                    evidence_content = '<p class="muted">请求摘要未记录，完整内容见原始证据。</p>'
                    if summary:
                        try:
                            event = json.loads(summary)
                            evidence_content = ('<div class="http-line"><strong>' + e(event.get('method', '')) +
                                '</strong><code>' + e(event.get('path', '')) + '</code>' +
                                ('<span>HTTP ' + e(event['status']) + '</span>' if 'status' in event else '') + '</div>')
                            for key, label in [('request', '请求'), ('response', '响应'), ('transportError', '传输异常')]:
                                if key in event:
                                    evidence_content += '<div class="payload"><span>' + label + '</span><pre>' + e(
                                        json.dumps(event[key], ensure_ascii=False, separators=(',', ':'))) + '</pre></div>'
                        except ValueError:
                            evidence_content = f'<pre>{e(summary)}</pre>'
                    evidence_rows.append(
                        f'<article class="evidence-entry" id="{anchor}"><h3>E{number} · {e(task["id"])} / {e(case["id"])}</h3>'
                        f'<p class="fine">{e(case["title"])}</p>' +
                        evidence_content +
                        '<p class="evidence-ids"><span>原始证据编号</span>' +
                        ' '.join(f'<code>{e(entry["id"])}</code>' for entry in case['evidence']) + '</p></article>')
                attention.append(
                    f'<article class="case-card {tone[group["state"]]}"><div class="card-heading">'
                    f'{badge(labels[group["state"]], tone[group["state"]])}<h3>{e(task["id"])} / {e(case["id"])} · {e(case["title"])}</h3></div>'
                    f'<div class="observation"><span>实际观察</span><p>{e(case["detail"])}</p></div>{reference}</article>')
        passed = [case for group in task['groups'] if group['state'] == 'PASS' for case in group['cases']]
        if passed:
            checks.append('<section class="passed-section"><table class="check-table">'
                          '<colgroup><col style="width:50%"><col style="width:50%"></colgroup><thead><tr><th colspan="2">' +
                          heading(task['id'] + ' · 已通过', badge(str(len(passed)) + ' 项', 'pass')) + '</th></tr></thead><tbody>')
            for index in range(0, len(passed), 2):
                cells = []
                for case in passed[index:index + 2]:
                    cells.append(f'<td><span class="case-id">{e(case["id"])}</span>{e(case["title"])}</td>')
                checks.append('<tr>' + ''.join(cells) + ('<td></td>' if len(cells) == 1 else '') + '</tr>')
            checks.append('</tbody></table></section>')

    if not attention:
        if total:
            attention.append('<p class="clear-result">本轮已执行检查全部通过。</p>')
        else:
            attention.append('<p class="muted">请先完成材料核对或执行环境准备。</p>')
    scope = []
    for task in view['tasks']:
        if task['notAssessed']:
            scope.append(f'<div class="scope-row"><strong>{e(task["id"])}</strong><ul>' +
                         ''.join(f'<li>{e(value)}</li>' for value in task['notAssessed']) + '</ul></div>')
    fields = list(view['identity'])
    for task in view['tasks']:
        for label, value in task['identity']:
            fields.append((task['id'] + ' · ' + label, value))
    short = [(label, value) for label, value in fields if len(str(value)) <= 28 and '时间' not in label]
    long = [(label, value) for label, value in fields if len(str(value)) > 28 or '时间' in label]
    audit = []
    for index in range(0, len(short), 2):
        cells = ''.join(f'<th>{e(label)}</th><td>{e(value)}</td>' for label, value in short[index:index + 2])
        audit.append('<tr>' + cells + ('<th></th><td></td>' if index + 1 == len(short) else '') + '</tr>')
    for label, value in long:
        audit.append(f'<tr><th>{e(label)}</th><td colspan="3">{e(value)}</td></tr>')
    appendix = heading('记录与版本') + '<table class="audit-table"><tbody>' + ''.join(audit) + '</tbody></table>'
    if evidence_rows:
        appendix += heading('关键证据') + ''.join(evidence_rows)
    template = Template((TEMPLATES / 'report.html').read_text(encoding='utf-8'))
    return template.substitute(
        css=(TEMPLATES / 'report.css').read_text(encoding='utf-8'),
        title=e(view['title']), candidate=e(identity['候选人']),
        submission=e(identity['提交版本']), release=e(identity['题包版本']),
        attempt=e(identity['执行轮次']), state=badge(state_label, state_tone),
        overview=''.join(overview), attention=''.join(attention), checks=''.join(checks),
        scope=(heading('未评估范围') + ''.join(scope)) if scope else '',
        appendix_class='appendix' if total else 'appendix continuous',
        appendix=appendix)


def pdf_bytes(view):
    """Print the same escaped HTML template using an offline Chromium document."""
    from playwright.sync_api import sync_playwright
    html = html_report(view)
    # Each download owns its browser and context; no HR cookie, URL or uploaded
    # candidate HTML is loaded. Serialize exports to bound browser memory use.
    with _pdf_lock, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, timeout=20000,
                    executable_path=os.environ.get('HR_PDF_BROWSER_PATH') or None)
        try:
            context = browser.new_context(java_script_enabled=False, service_workers='block')
            context.route('**/*', lambda route: route.abort())
            page = context.new_page()
            page.set_default_timeout(15000)
            page.set_content(html, wait_until='load')
            return page.pdf(
                format='A4', print_background=True, prefer_css_page_size=True,
                display_header_footer=True, header_template='<span></span>',
                footer_template=(
                    '<div style="width:100%;margin:0 16mm;font-family:Arial,sans-serif;'
                    'font-size:8px;color:#7b8796;display:flex;justify-content:space-between;">'
                    '<span>' + escape(str(dict(view['identity'])['候选人'])) + '</span><span><span class="pageNumber"></span>'
                    ' / <span class="totalPages"></span></span></div>'),
                tagged=True, outline=True)
        finally:
            browser.close()
