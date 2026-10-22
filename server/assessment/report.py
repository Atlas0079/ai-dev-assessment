"""Objective evidence first; subjective advice is explicitly disabled and empty."""
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

from .catalog import BUSINESS_LINES, QUESTIONS, question
from .evaluate import RESULT_SCHEMA_VERSION, subjective_placeholder, unexecuted_result

CASE_GROUPS = (('FAIL', '未通过', '未通过的用例'),
               ('NOT_RUN', '未完成', '未执行或未完成的用例'),
               ('ERROR', '检查异常', '检查异常'), ('PASS', '已通过', '已通过的用例'))


def plain(value):
    text = str(value).replace('\r', ' ').replace('\n', ' ')
    return re.sub(r'([\\\x60*_{}\[\]()<>#!|])', r'\\\1', text)


def validate_result(result):
    if result.get('resultSchemaVersion') != RESULT_SCHEMA_VERSION:
        raise ValueError('结果格式不匹配，请使用当前检查器重新生成；不会自动兼容旧结果。')
    spec = question(result['task'])
    if result['evaluationType'] != 'objective' or result['businessLine'] != spec.business_line:
        raise ValueError('结果的评测类型或业务线与题目不一致')
    if result['subjective'] != subjective_placeholder():
        raise ValueError('主观评价尚未启用，建议必须为空')
    if result['status'] not in ('CHECKED', 'NOT_RUN'):
        raise ValueError('未知执行状态')
    if result['status'] == 'NOT_RUN' and result['cases']:
        raise ValueError('未执行的题目不能含有用例结果')
    ids = [case['id'] for case in result['cases']]
    if len(ids) != len(set(ids)):
        raise ValueError('用例编号重复')
    if any(case['status'] not in ('PASS', 'FAIL', 'NOT_RUN', 'ERROR') for case in result['cases']):
        raise ValueError('未知用例状态')
    if any(not re.fullmatch(r'EV-[A-Za-z0-9-]+', eid)
           for case in result['cases'] for eid in case['evidenceIds']):
        raise ValueError('非法证据编号')


def report_facts(results, submitted=None):
    """Normalize scope, execution qualifications and ordered cases for all reports."""
    submitted = list(submitted) if submitted is not None else [r['task'] for r in results]
    if len(submitted) != len(set(submitted)):
        raise ValueError('提交题目重复')
    for task in submitted:
        question(task)
    by_task = {}
    for result in results:
        validate_result(result)
        task = result['task']
        if task not in submitted or task in by_task:
            raise ValueError('测试结果必须唯一对应已提交的题目')
        by_task[task] = result
    for task in submitted:
        if task not in by_task:
            by_task[task] = unexecuted_result(task)
    rows = []
    for task in submitted:
        result = by_task[task]
        notes = []
        if result['execution'].get('mode', '').startswith('trusted'):
            notes.append('内部可信参考程序验证，非候选人答案运行。')
        if result['execution'].get('modelMode') == 'fixture':
            notes.append('模型替身验证，不代表真实模型通过。')
        rows.append(dict(id=task, title=question(task).title, result=result, notes=notes,
                         groups=[dict(state=state, title=title, markdownTitle=heading,
                                      cases=[case for case in result['cases'] if case['status'] == state])
                                 for state, title, heading in CASE_GROUPS]))
    return dict(submitted=submitted, unsubmitted=[task for task in QUESTIONS if task not in submitted],
                results=by_task, tasks=rows)


def write_report(results, output, candidate_id='未指定', submitted=None, result_sources=None):
    output = Path(output)
    sources = result_sources or {}
    facts = report_facts(results, submitted)
    submitted, by_task = facts['submitted'], facts['results']

    def evidence_link(task, filename, label):
        if task not in sources:
            return plain(label) + '（未提供证据目录）'
        path = Path(sources[task]).resolve() / filename
        if not path.is_file():
            return plain(label) + '（证据文件缺失，需复核）'
        try:
            target = quote(Path(os.path.relpath(path, output.parent.resolve())).as_posix(), safe='/')
        except ValueError:
            target = path.as_uri()
        return '[' + plain(label) + '](' + target + ')'

    lines = ['# 候选人检查结果', '', '候选人：' + plain(candidate_id), '',
             '所有题目均为选做。本报告直接提供结果，不打分、不排名、不作录用判断。', '',
             '## 选题情况', '', '| 业务线 | 题目 | 提交与执行情况 |', '|---|---|---|']
    for task in QUESTIONS:
        spec = question(task)
        if task not in submitted:
            state = '未提交／未选做（不计作测试失败）'
        elif by_task[task]['status'] == 'NOT_RUN':
            state = '已提交，未执行'
        else:
            state = '已提交，结果见下文'
        lines.append(f'| {plain(BUSINESS_LINES[spec.business_line])} | {plain(task + " · " + spec.title)} | {state} |')

    lines += ['', '## 客观测试结果', '']
    if not submitted:
        lines += ['没有已提交题目，不生成测试结论。', '']
    for row in facts['tasks']:
        task, result = row['id'], row['result']
        spec = question(task)
        lines += ['### ' + plain(task + ' · ' + spec.title), '',
                  '业务线：' + plain(BUSINESS_LINES[spec.business_line]), '',
                  '检查版本：' + plain(result['checkVersion']), '',
                  '检查时间（UTC）：' + plain(result['evaluatedAt'] or '未执行'), '',
                  '执行方式：' + plain(json.dumps(result['execution'], ensure_ascii=False)), '']
        if result['status'] == 'NOT_RUN':
            lines += [*result['notAssessed'], '']
            continue
        for note in row['notes']:
            lines += ['**' + plain(note) + '**', '']
        for group in row['groups']:
            status, heading, cases = group['state'], group['markdownTitle'], group['cases']
            lines += ['#### ' + heading, '']
            if not cases:
                lines.append('无此类记录。')
            for case in cases:
                lines.append('- ' + plain(case['id'] + '：' + case['title']))
                if status != 'PASS':
                    lines.append('  - 实际观察：' + plain(case['detail']))
                    links = []
                    for eid in case['evidenceIds']:
                        links.append(evidence_link(task, 'evidence/' + eid + '.json', eid))
                    lines.append('  - 证据：' + ('、'.join(links) if links else '无请求响应证据，需复核检查记录。'))
            lines.append('')
        lines += ['#### 未评估范围', '']
        lines += ['- ' + plain(item) for item in result['notAssessed']]
        lines += ['', '完整用例记录：' + evidence_link(task, 'cases.json', 'cases.json'), '']
    lines += ['候选人自述未自动收录，请结合提交项目 README；自述不等同于验证结果。', '',
              '## 主观评价', '', '状态：未启用。架构、网页美观等暂不评价，不计入客观用例状态。', '',
              '### LLM 建议', '', '']
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines), encoding='utf-8')
