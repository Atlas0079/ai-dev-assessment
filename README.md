# 招聘题库与可执行检查 2.0

独立仓库位置：`C:\MyResearch\buge\ai-dev-assessment`。本地验证工具位于被Git忽略的`.runtime/tools`，运行`python scripts/configure-local.py`可重建本机路径配置，也支持JAVA、MONGOD环境变量。无需依赖原Codex工作区。

生成的发题包位于`dist/candidate-exam.zip`，内部源码包位于`releases/assessment-tools-source.zip`；两类生成物均不进入Git。`docs/03-现有服务端技术蓝本对照.md`保留历史调研快照，当前实现范围以本README、题面及验证记录为准。

当前交付是GAME/ORDER题目、接口契约、参考实现和命令行检查工具。没有HR控制台、自动收包、任务队列、雷达图、综合分数或录用建议。WORKFLOW仅保留设计草案，不执行、不计分。原版自动计分规则、关键词工作流与旧浏览器检查已撤回。

## 发题与交付

发给候选人的材料是 dist/candidate-exam.zip，包含GAME与ORDER题面、起始工程、提交模板，以及明确标为暂缓的WORKFLOW设计草案。内部 references、order-reference、assessment 和 tests含答案/检查器，不可当发题包发送。

提交文件名约定 C20260001_v1.zip；根目录submission.json与GAME/ORDER工程。HR人工收发；此命名约定目前写入说明，尚无自动上传校验。

GAME要求受保护的牌局注入及完整状态接口，详见questions/GAME/测试接口与数据契约.md及samples。正常业务状态与测试状态共用规则。ORDER沿用起始Java8/Mongo工程及接口。

## 执行

```powershell
python scripts/build-packs.py
python -m unittest discover -s tests -v
python scripts/smoke.py
python scripts/verify-defects.py
python scripts/package-release.py
```

smoke仅启动本仓库可信参考实现。ORDER需要本地Java8、已构建的JAR与MongoDB；通过scripts/bootstrap.ps1配置。当前启动器不会在缺少MongoDB时降级为内存实现。构建是否成功不由启动器预先标记。

检查已在隔离测试环境启动的服务：

```powershell
$env:EVAL_CONTROL_TOKEN='填写与游戏服务相同的临时测试令牌'
python scripts/check.py GAME --url http://127.0.0.1:8080
python scripts/check.py ORDER --url http://127.0.0.1:8080
```

命令行检查会写入虚构牌局/订单，必须使用独立测试服务和数据库。只有HTTP地址时ORDER的数据库故障与重启检查显示NOT_RUN。这个命令不会自动解压、构建或运行受试者ZIP。

## 结果含义

result.json包含逐用例状态、按维度分组的状态数量、未评估事项；cases.json与evidence/保留证据。PASS是断言通过，FAIL是业务不符合，NOT_RUN是前置能力缺失或连接问题，ERROR需要复核检查器/契约异常。无score、总分、排名或雷达图。退出码0表示本次注册的全部检查通过，不意味着题目或候选人整体合格；非零表示有失败、未执行或错误。

verify-defects使用参考实现的独立副本注入已知错误，检查指定用例是否真正报FAIL，不修改原参考实现，也不执行任何候选人代码。其结果只支持列出的缺陷能够被发现。

## Docker与剩余范围

assessment/runner.py保留专用Linux评测节点的Docker组件：构建、资源限制、内网容器、注入GAME控制令牌和ORDER数据库。当前机器没有Docker/WSL，容器链路未实机验证；不能承诺任意候选人代码安全运行或部署完成。公司普通内网Java服务器不应直接当作执行不可信代码的宿主，后续需要独立隔离节点。

未完成：HR网页及完整收包链路、公司服务器部署、Docker实机验证、浏览器体验检查、评分权重校准、雷达图、LLM审查与AI工作流实施。实际已运行的证据见docs/验证记录.md。
