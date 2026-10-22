'use strict';
const $ = id => document.getElementById(id);
let releases = [], selected = null, selectedAttempt = null, selectedStamp = null, busy = false, loggedIn = false;
let reportRequest = 0;
const settled = job => !['QUEUED', 'RUNNING'].includes(job.state);
function text(tag, value, className) { const node = document.createElement(tag); node.textContent = value; if (className) node.className = className; return node; }
function message(id, value) { $(id).textContent = value || ''; $(id).hidden = !value; }
function loginView() { reportRequest++; loggedIn = false; $('workspace').hidden = true; $('login-panel').hidden = false; $('download-pack').hidden = true; $('logout').hidden = true; }
async function api(path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', ...options });
  const value = await response.json();
  if (!response.ok) { if (response.status === 401) loginView(); throw new Error(value.message || '请求失败，请重试。'); }
  return value;
}
function reportLink(job) { return `/api/jobs/${job.id}/report.pdf?attempt=${job.attempt}`; }
function chooseRelease() {
  const value = releases.length === 1 ? releases[0].version : $('release').value;
  $('download-pack').href = `/api/packages/${encodeURIComponent(value)}/candidate-exam.zip`;
  return value;
}
function action(label, callback) { const button = text('button', label); button.type = 'button'; button.addEventListener('click', callback); return button; }
async function refreshJobs() {
  const jobs = await api('/api/jobs');
  const body = $('records'); body.replaceChildren();
  if (!jobs.length) { const row = document.createElement('tr'); const cell = text('td', '暂无记录', 'empty'); cell.colSpan = 5; row.append(cell); body.append(row); }
  for (const job of jobs) {
    const row = document.createElement('tr');
    row.append(text('td', job.candidateId), text('td', job.submissionVersion === null ? '未识别' : `v${job.submissionVersion}`));
    const state = document.createElement('td');
    state.append(text('span', job.state === 'COMPLETED' && job.hasFailures ? '已完成，有未通过项' : job.stateLabel, `state state-${job.state}`));
    if (!settled(job)) state.append(text('div', job.stage, 'stage'));
    row.append(state, text('td', new Date(job.createdAt).toLocaleString('zh-CN', { hour12: false }), 'time'));
    const cell = document.createElement('td'), actions = document.createElement('div'); actions.className = 'row-actions';
    actions.append(action('查看', () => openReport(job.id).catch(e => message('service-error', e.message))));
    if (settled(job)) { const link = text('a', '下载报告'); link.href = reportLink(job); actions.append(link); }
    if (job.canRetry) actions.append(action('重试', async event => {
      const button = event.currentTarget; button.disabled = true;
      try { await api(`/api/jobs/${job.id}/retry`, { method: 'POST', body: '' }); await refreshJobs(); if (selected === job.id) await openReport(job.id); }
      catch (e) { message('service-error', e.message); button.disabled = false; }
    }));
    cell.append(actions); row.append(cell); body.append(row);
  }
  message('service-error', '');
  if (selected && selectedAttempt === null) { const job = jobs.find(j => j.id === selected); if (job && job.updatedAt !== selectedStamp) await openReport(selected); }
}
async function openReport(id, attempt = null) {
  const request = ++reportRequest;
  $('report-download').hidden = true; $('attempt').disabled = true;
  let response;
  try { response = await api(`/api/jobs/${id}${attempt === null ? '' : '?attempt=' + attempt}`); }
  finally { if (request === reportRequest) $('attempt').disabled = false; }
  if (request !== reportRequest) return;
  const { job, report } = response;
  selected = id; selectedAttempt = job.attempt < job.currentAttempt ? job.attempt : null; selectedStamp = job.updatedAt; location.hash = id;
  $('report-title').textContent = `结果：${job.candidateId}`;
  $('report-download').href = reportLink(job); $('report-download').hidden = !settled(job);
  $('attempt-field').hidden = job.currentAttempt <= 1;
  $('attempt').replaceChildren(...Array.from({ length: job.currentAttempt }, (_, index) => {
    const number = job.currentAttempt - index, option = text('option', `第 ${number} 次${number === job.currentAttempt ? '（当前）' : ''}`);
    option.value = number; option.selected = number === job.attempt; return option;
  }));
  const content = $('report-content'); content.replaceChildren();
  const metadata = document.createElement('div'); metadata.className = 'metadata';
  for (const [label, value] of report.identity) { const item = text('div', label); item.append(text('span', value)); metadata.append(item); }
  content.append(metadata);
  if (report.unsubmitted.length) content.append(text('p', '未选做：' + report.unsubmitted.join('、'), 'scope'));
  for (const issue of report.issues) {
    const block = document.createElement('div'); block.className = 'issue';
    block.append(text('p', (issue.task ? `${issue.task}：` : '') + issue.message), text('p', `下一步：${issue.action}`));
    block.append(text('p', `责任：${issue.ownerLabel} · ${issue.stage}`, 'issue-meta'));
    if (issue.cases.length) block.append(text('p', '受影响用例：' + issue.cases.join('、'), 'issue-meta'));
    if (issue.faultId) block.append(text('p', '故障编号：' + issue.faultId, 'issue-meta'));
    content.append(block);
  }
  for (const task of report.tasks) {
    content.append(text('h3', `${task.id} · ${task.title}`));
    for (const [label, value] of task.identity) content.append(text('p', `${label}：${value}`, 'scope'));
    for (const note of task.notes) content.append(text('p', note, 'note'));
    for (const group of task.groups) {
      const details = document.createElement('details'); details.open = group.state !== 'PASS';
      details.append(text('summary', `${group.title} ${group.cases.length} 项`));
      for (const item of group.cases) {
        const block = document.createElement('div'); block.className = 'case'; block.append(text('p', `${item.id}：${item.title}`, 'case-title'));
        if (group.state !== 'PASS') {
          block.append(text('p', item.detail, 'case-detail'));
          const evidence = document.createElement('div'); evidence.className = 'evidence';
          for (const entry of item.evidence) { const link = text('a', entry.id); link.href = entry.url; link.target = '_blank'; link.rel = 'noopener'; evidence.append(link); }
          if (item.evidence.length) block.append(evidence);
        }
        details.append(block);
      }
      content.append(details);
    }
    if (task.notAssessed.length) { const details = document.createElement('details'); details.append(text('summary', '未评估范围')); for (const line of task.notAssessed) details.append(text('p', line, 'scope')); content.append(details); }
  }
  content.append(text('p', '主观评价：未启用。LLM 建议留空。', 'subjective'));
  $('report-panel').hidden = false;
}
async function initialize() {
  message('global-error', '');
  const session = await api('/api/session');
  if (!session.authenticated) { loginView(); return; }
  loggedIn = true; $('workspace').hidden = false; $('login-panel').hidden = true; $('logout').hidden = !session.loginRequired;
  releases = await api('/api/releases');
  $('release').replaceChildren(...releases.map(item => { const option = text('option', item.version + (item.submissionAllowed ? '' : '（仅留存）')); option.value = item.version; option.disabled = !item.submissionAllowed; return option; }));
  $('release').hidden = releases.length === 1; $('single-release').hidden = releases.length !== 1;
  $('single-release').value = releases[0].version; chooseRelease(); $('download-pack').hidden = false;
  const status = await api('/api/status');
  if (status.blocked.length === status.taskCount) message('environment', '评测环境未就绪。答案可上传保存，环境恢复后可重试。');
  else if (status.blocked.length) message('environment', status.blocked.map(i => i.task).join('、') + ' 暂不可评测，上传后会记录平台原因。');
  else message('environment', '');
  await refreshJobs();
  if (/^[a-f0-9]{32}$/.test(location.hash.slice(1))) await openReport(location.hash.slice(1));
}
$('release').addEventListener('change', chooseRelease);
$('attempt').addEventListener('change', () => openReport(selected, Number($('attempt').value)).catch(e => message('service-error', e.message)));
$('upload-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  const file = $('answer').files[0];
  if (!file || file.size > 100 * 1024 * 1024) { message('upload-error', '请选择不超过 100 MB 的 ZIP。'); return; }
  busy = true; $('upload').disabled = true; $('upload').textContent = '上传中…'; message('upload-error', '');
  try {
    const job = await api('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/zip', 'X-Submission-Filename': encodeURIComponent(file.name), 'X-Release-Version': chooseRelease() }, body: file });
    await refreshJobs(); await openReport(job.id); $('answer').value = '';
  } catch (e) { message('upload-error', e.message); }
  finally { busy = false; $('upload').disabled = false; $('upload').textContent = '上传并评测'; }
});
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); message('login-error', '');
  try { await api('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: $('password').value }) }); $('password').value = ''; await initialize(); }
  catch (e) { message('login-error', e.message); }
});
$('logout').addEventListener('click', async () => { try { await api('/api/logout', { method: 'POST', body: '' }); selected = null; selectedAttempt = null; selectedStamp = null; $('records').replaceChildren(); $('report-content').replaceChildren(); $('report-panel').hidden = true; location.hash = ''; loginView(); } catch (e) { message('service-error', e.message); } });
$('refresh').addEventListener('click', () => initialize().catch(e => message('service-error', e.message)));
$('close-report').addEventListener('click', () => { reportRequest++; selected = null; selectedAttempt = null; selectedStamp = null; location.hash = ''; $('report-panel').hidden = true; });
setInterval(() => { if (loggedIn && !busy && !document.hidden) refreshJobs().catch(e => message('service-error', e.message)); }, 3000);
initialize().catch(e => message('global-error', e.message));
