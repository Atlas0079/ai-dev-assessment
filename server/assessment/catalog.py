"""Question metadata shared by checks, reports and distribution. No scoring rules."""
from dataclasses import dataclass
from typing import Callable

from .game_checks import game_checks
from .order_checks import order_checks
from .workflow_checks import workflow_checks

BUSINESS_LINES = {
    'SOCIAL_PLATFORM': '社交平台开发',
    'SOCIAL_GAME': '平台内社交小游戏',
    'INTERNAL_AI': '组织内部员工提效',
}
CAPABILITIES = {'AI_DEVELOPMENT': '用 AI 开发', 'AI_INTEGRATION': '把 AI 集成到工作'}


@dataclass(frozen=True)
class Question:
    title: str
    business_line: str
    capabilities: tuple[str, ...]
    checker: Callable
    check_version: str
    public_docs: tuple[str, ...]
    pack_profile: str
    example_filename: str | None = None
    timeout: int = 10
    not_assessed: tuple[str, ...] = ()


# Every question is optional. A business line may contain multiple questions.
QUESTIONS = {
    'GAME': Question(
        title='多人 UNO 简化版', business_line='SOCIAL_GAME',
        capabilities=('AI_DEVELOPMENT',), checker=game_checks, check_version='2.0',
        public_docs=('README.md', 'samples/fixture.json', 'samples/fixture.schema.json'),
        pack_profile='game', example_filename='示例游戏_13800000001_v1.zip',
        not_assessed=('页面实际操作、三秒同步与刷新恢复',)),
    'ORDER': Question(
        title='接手模拟订单服务', business_line='SOCIAL_PLATFORM',
        capabilities=('AI_DEVELOPMENT',), checker=order_checks, check_version='2.0',
        public_docs=('README.md',),
        pack_profile='order', example_filename='示例订单_13800000002_v1.zip',
        not_assessed=('页面实际操作', '生产负载下的性能')),
    'WORKFLOW': Question(
        title='订单售后申请助手', business_line='INTERNAL_AI',
        capabilities=('AI_INTEGRATION',), checker=workflow_checks, check_version='2.1-workflow',
        public_docs=('README.md',),
        pack_profile='workflow', example_filename='示例工作流_13800000003_v1.zip', timeout=300,
        not_assessed=('页面实际操作', '自由文本完整事实性、表达与共情',
                      '实际岗位人工基线与提效', '所有提示注入与故障时序')),
}


def question(task):
    try:
        value = QUESTIONS[task]
    except KeyError:
        raise ValueError('未知题目：' + str(task)) from None
    if value.business_line not in BUSINESS_LINES:
        raise ValueError('题目业务线未注册：' + task)
    if any(capability not in CAPABILITIES for capability in value.capabilities):
        raise ValueError('题目考察能力未注册：' + task)
    if value.pack_profile not in {'game', 'order', 'workflow'}:
        raise ValueError('题目运行类型未注册：' + task)
    return value


def public_catalog():
    """Only public metadata; never checker code or internal case catalogs."""
    return [dict(id=task, title=value.title, businessLine=value.business_line,
                 businessLineName=BUSINESS_LINES[value.business_line],
                 capabilities=[CAPABILITIES[c] for c in value.capabilities], optional=True)
            for task in QUESTIONS for value in (question(task),)]
