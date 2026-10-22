# 内部示例答案

三份示例均为招聘方编写，目录与候选人实际提交一致。示例不进入发题包。

| 题目 | 源码 | 提交包 |
|---|---|---|
| GAME | [game-submission/GAME](game-submission/GAME/README.md) | server/releases/示例游戏_13800000001_v1.zip |
| ORDER | [order-submission/ORDER](order-submission/ORDER/README.md) | server/releases/示例订单_13800000002_v1.zip |
| WORKFLOW | [workflow-submission/WORKFLOW](workflow-submission/WORKFLOW/README.md) | server/releases/示例工作流_13800000003_v1.zip |

示例姓名和号码仅用于内部测试。身份和版本来自 ZIP 文件名，选题来自根目录的工程目录。

在 server 目录运行 `python scripts/build-examples.py`，生成三份 ZIP 和 example-release.json。打包前按当前固定环境校验，保留原始 Dockerfile；ORDER 同时保留三个原始 POM。包中无仓库路径导入、故障开关、个人凭据或额外第三方依赖。

GAME 包含完整牌局与玩家网页，ORDER 包含订单迁移、权限与 MongoDB 持久化实现，WORKFLOW 包含模型工具调用及确认建单流程。每题的启动和实现说明见工程内 README.md，业务契约以候选人题面为准。

示例文件名在 assessment/catalog.py 的题目登记中维护，examples.py 据此生成示例清单。构建示例包后，通过 HR 上传验证完整链路；可信本机、真实容器与模型替身结果分别记录。当前结果、原始证据索引及部署源码包发布顺序统一见维护仓库本地的 docs/目前实现文档.md 第 2、5 节；该文档与运行证据不包含在部署源码包中。
