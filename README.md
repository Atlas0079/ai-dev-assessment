# AI 全栈招聘评测

三道选做题考察「用 AI 开发」和「把 AI 集成到工作」。系统提供客观检查和证据，不评分、不排名、不作录用判断；主观评价暂未启用。

使用流程：负责人部署与发布 → HR 发题 → 候选人开发、自测并提交 → HR 网页上传 → 系统隔离构建、运行、检查并保存结果 → HR 下载 PDF 转交面试官。

## 文档入口

| 读者与用途 | 入口 |
|---|---|
| 项目目标、责任与验收要求 | 本地维护资料：docs/预期文档.md |
| 实际调用链、部署操作、验证范围与剩余工作 | 本地维护资料：docs/目前实现文档.md |
| HR 发题、上传、补交、故障联系与报告转交 | 本地维护资料：docs/HR操作SOP.md |
| 候选人选题、固定环境与开发说明 | [候选人总包说明](candidate/README.md) |
| 内部示例的源码与打包入口 | [内部示例答案](server/internal/examples/README.md) |

## 目录与操作入口

```text
server/      服务端工程、打包工具与内部验证资源
candidate/   可编辑题目、固定环境与生成的唯一总包
docs/        目标、实现与 HR 操作说明
```

题面在 candidate/tasks 中直接维护：[GAME](candidate/tasks/GAME/README.md)、[ORDER](candidate/tasks/ORDER/README.md)、[WORKFLOW](candidate/tasks/WORKFLOW/README.md)。在 server 目录运行 `python scripts/build-packs.py` 生成 candidate/candidate-exam.zip；服务入口为 server/scripts/hr-server.py，默认数据目录为 server/.runtime/hr。部署准备、发布步骤和本机预览入口统一见目前实现文档第 4 节。

当前仍有未验收范围，具体状态以目前实现文档为准。辅助测试与文档按协作约定仅本地保留。

## 工程运行与基础检查

使用 Python 3.13.13，在 server 目录执行：

```bash
python -m unittest discover -s tests -v
python scripts/build-packs.py
python scripts/build-examples.py
```

默认测试只执行仓库基础回归，题包在临时目录构建，无需预先生成 ZIP、浏览器、MongoDB 或本机历史运行数据。本地辅助回归与环境集成检查分别放在 tests/local 和 tests/integration，均不随 Git 分发；不放置 `__init__.py`，避免默认发现递归纳入这些检查。

正式运行需要专用 Linux Docker 节点；安装服务依赖、PDF 浏览器与中文字体后，在 server 执行 `python scripts/prepare-environment.py prepare`。设置 `ASSESSMENT_DEDICATED_SANDBOX=1` 和 `HR_ACCESS_PASSWORD`，再运行 `python scripts/hr-server.py --host 0.0.0.0 --port 8088`；内网访问另配置 HTTPS，反向代理下加 `--secure-cookie`。WORKFLOW 正式执行还需要部署方模型凭据，真实模型验证尚未完成。
