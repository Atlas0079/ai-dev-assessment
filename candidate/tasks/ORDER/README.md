# ORDER｜接手社交平台的订单服务

## 1. 任务概览

你接手一个已有的模拟订单项目。登录、服务列表、创建订单、查询列表和基础页面已经存在，但接单、取消、完成尚未实现，订单详情还存在权限缺陷。请在现有项目上补齐这些能力，使订单在重复请求、多人竞争、数据库故障及服务重启后仍保持正确。

允许使用熟悉的 AI 编码工具。本题不要求接入模型服务，不涉及真实支付或退款。

三题全部选做，可只做本题或选择多题。

**本文件包含本题全部说明**：已有材料、开发范围、业务规则、完整接口、启动自测及提交验收。

## 2. 已有项目与需要修改的部分

### 2.1 题包内容

| 路径 | 内容 |
|---|---|
| `README.md` | 本题完整说明 |
| `ORDER/` | Java 8、Spring Boot 2.1.13、Maven 双模块起始项目，含 Dockerfile |
| `ORDER/order-api/` | 订单模型和业务接口 |
| `ORDER/order-application/` | Controller、Service、状态规则、MongoDB DAO 和基础网页 |
| `devtools/` | 公开自测脚本 |
| `compose.yaml` | 应用、MongoDB 及公开自测的启动配置 |

保留现有框架、模块分层和 HTTP 接口。Java 8、Maven 3.9.9、Spring Boot 2.1.13.RELEASE、MongoDB 7.0.16 及工程依赖固定，不能增加依赖或构建插件。继续通过 MongoTemplate 操作 MongoDB，补齐现有项目内的实现。

### 2.2 接口与职责

| 部分 | 当前状态 | 你的工作 |
|---|---|---|
| `/healthz`、演示登录、服务列表 | 已实现 | 保持可用 |
| 创建订单、查询列表 | 已实现 | 保持原功能和接口格式 |
| 查询订单详情 | 接口已存在，但缺少归属权限校验 | 修复越权读取 |
| 接单、取消、完成 | Controller 路径已存在，业务为 TODO | 在原有业务链路内实现 |
| MongoDB DAO | 已提供读取、插入、按版本更新等能力 | 结合现有能力保证持久化与并发正确性 |
| 基础网页 `/` | 已提供登录、建单、列表和订单操作入口 | 让现有操作随业务实现正常工作 |

浏览器和检查程序调用你交付的订单应用，由它通过 MongoDB 保存和读取数据。

优先阅读 `OrderController.java`、`OrderService.java`、`Transitions.java`、`OrderOperations.java`、`OrderDao.java` 和 `MongoOrderDao.java`。其中业务入口为：

```java
Map<String,Object> transition(String orderId, String user, String action, String key, String note)
```

`OrderService` 负责业务编排，`Transitions` 中补齐状态和角色规则；保留现有分层。详情归属校验的待修复位置已在 Controller 标记。

## 3. 业务规则

### 3.1 身份、服务和价格

使用四个虚构账号：`customer1`、`customer2` 是客户，`provider1`、`provider2` 是服务者。通过演示登录接口换取令牌，后续身份以令牌为准，不信任请求体中的身份字段。

服务列表提供 `s1`，价格为 `3000` 分。客户创建订单时提交 `serviceId`；价格由服务端决定，即使请求携带更低的 `amountFen` 也不能改变价格。本题仅模拟已支付订单，不实现支付流程。

### 3.2 状态与角色

新订单为 `PENDING`，`providerId=null`，`version=0`。

| 当前状态 | 操作 | 允许的操作者 | 成功后的状态 |
|---|---|---|---|
| `PENDING` | accept 接单 | 任一服务者 | `ACCEPTED`，绑定该服务者 |
| `PENDING` | cancel 取消 | 订单所属客户 | `CANCELLED` |
| `ACCEPTED` | complete 完成 | 已接单的服务者 | `COMPLETED` |

`CANCELLED` 和 `COMPLETED` 为终态。客户不能接单，其他服务者不能代为完成，接单后的订单不能走本题的取消流程。成功状态迁移使 `version` 恰好加 1。

客户只能查看自己的订单；服务者可以看待接订单的公开摘要，以及自己已接的订单。列表和详情都要符合归属规则，不能借详情接口看到其他客户或服务者的受限订单。公开字段见第 4.3 节，不返回内部幂等记录。

### 3.3 幂等与并发

“幂等”在本题指网络重试不会把同一操作执行两次。每次迁移要求非空 `Idempotency-Key`。在同身份、同订单、同动作下，相同 key 和相同 `note` 重试，返回第一次成功时的结果；即使订单后来又发生迁移，也返回该次原结果。相同 key 换 `note` 返回 409。

同一订单被多人同时接单时，只能一人成功；接单与取消竞争，也只能产生一个合法结果。失败操作不改变订单或版本，重复请求不能再次增加版本。

### 3.4 数据库故障与重启

订单状态和幂等回执都需要持久化。数据库断开、恢复和请求重试后，不能出现“迁移已成功但回执丢失，因此再次执行”的情况。服务重启后，已创建订单和成功操作的回执仍应有效。

使用 `MONGO_URI` 指定的 MongoDB，不能靠内存副本绕过数据库故障。MongoDB 自带 `_id` 唯一索引；注意实体 `id` 映射，不要对可能不存在的普通 `id` 字段建立导致 `null` 冲突的唯一索引。

数据库断网与进程重启由招聘方的运行环境控制，**不要求你添加“断网”“重启”等 HTTP 测试接口**。

## 4. HTTP 接口

### 4.1 地址、包装和认证

应用监听 `0.0.0.0:8080`，本地访问 `http://127.0.0.1:8080`。JSON 使用 UTF-8，请求体使用 `Content-Type: application/json`。

业务成功均为 HTTP 200，包装为 `{"code":0,"data":返回值}`；错误使用实际 HTTP 状态和 `{"code":"错误标识"}`。`GET /healthz` 例外，直接返回 `{"status":"ok"}`，可含存储信息。

健康、演示登录和服务列表不需令牌；订单接口携带：

```http
Authorization: Bearer <登录接口返回的 token>
```

### 4.2 登录与服务列表（已有）

```http
POST /v1/demo-login
Content-Type: application/json

{"account":"customer1"}
```

成功响应：

```json
{"code":0,"data":{"token":"以实际响应为准"}}
```

其他三个账号同样登录。`GET /v1/services` 返回：

```json
{"code":0,"data":[{"id":"s1","title":"双人游戏陪练","amountFen":3000}]}
```

### 4.3 创建、列表、详情（保留并修复权限）

| 方法与路径 | 输入 | `data` 内容 |
|---|---|---|
| `POST /v1/orders` | `{"serviceId":"s1"}`，客户令牌 | 新订单对象 |
| `GET /v1/orders?page=1&size=2` | 令牌；页码从 1 开始 | `{"items":[订单对象],"total":可见订单总数}` |
| `GET /v1/orders/{id}` | 令牌 | 可见订单对象 |

创建响应示例：

```json
{
  "code":0,
  "data":{
    "id":"实际生成的订单ID","customerId":"customer1","providerId":null,
    "serviceId":"s1","status":"PENDING","amountFen":3000,"version":0
  }
}
```

订单对外使用这七个字段，不返回内部回执。列表默认 `page=1`、`size=10`，`size` 范围 1—100；`total` 是当前用户可见的订单数，不是全库订单数。

### 4.4 接单、取消、完成（需要实现）

三个接口请求格式相同：

```http
POST /v1/orders/<实际订单ID>/accept
Authorization: Bearer <provider1 的 token>
Idempotency-Key: accept-1
Content-Type: application/json

{"note":"接单备注"}
```

| 路径 | 操作者 | 成功 `data` |
|---|---|---|
| `/v1/orders/{id}/accept` | 服务者 | 订单状态 `ACCEPTED`、`providerId` 为该服务者、版本增加 1 |
| `/v1/orders/{id}/cancel` | 订单客户 | 订单状态 `CANCELLED`、版本增加 1 |
| `/v1/orders/{id}/complete` | 已接单服务者 | 订单状态 `COMPLETED`、版本增加 1 |

`data` 都为第 4.3 节的完整订单对象。新操作换新 key，重试原操作保留原 key 和请求体；不能把一个业务错误包装成 HTTP 200 成功。

### 4.5 错误状态

| 情况 | HTTP 状态 |
|---|---|
| 请求参数无效、缺少幂等 key | 400 |
| 未认证或令牌无效 | 401 |
| 操作者角色／归属不允许 | 403 |
| 订单不存在 | 404 |
| 非法状态迁移、幂等冲突、并发竞争失败 | 409 |

读取他人受限订单详情时，接受 403 或 404。错误体例如 `{"code":"FORBIDDEN"}`；页面应呈现失败，不能仍显示操作成功。

### 4.6 一次完整调用示例

1. 分别登录 `customer1` 与 `provider1`，保存两个 token。
2. 客户 POST `/v1/orders`，用实际返回的 `id` 继续，预期 `PENDING/version=0`。
3. 服务者带 `Idempotency-Key: accept-1` 接单，预期 `ACCEPTED/version=1`。
4. 原样重试接单，仍返回首次接单结果，不增加版本。
5. 同一服务者带新 key 完成，预期 `COMPLETED/version=2`。
6. 客户读取详情，应看到完成后的订单；再次重放第 3 步仍返回首次接单的响应快照，不能把当前订单退回接单状态。

## 5. 启动与自测

### 5.1 Docker 方式

本题使用总题包 `environment/` 中的固定环境。首次开发前，在当前 `tasks/ORDER/` 目录运行 `python ../../environment/fixed_runtime.py prepare`，准备过程需要 Docker、网络和磁盘；准备成功后再启动本题。环境说明和完整依赖清单见 [总包说明](../../README.md) 与 [固定依赖](../../environment/requirements.lock)。

使用题包提供的库及语言标准库，不新增或升级依赖。前端使用原生 HTML、CSS、JavaScript，资源随源码提交。保留原始 `Dockerfile` 和三个 `pom.xml`。

在**题目目录**运行；总题包先进入 `tasks/ORDER/`：

```powershell
docker compose up -d --build
docker compose logs app
```

此配置启动订单应用与 MongoDB。浏览器访问 `http://127.0.0.1:8080/`，健康地址为 `/healthz`。应用在容器中使用 `mongodb://mongo:27017/assessment`；MongoDB 不映射宿主机端口，数据保存在 `order-data` 卷。

运行公开自测：

```powershell
docker compose --profile check run --rm public-check
```

停止使用 `docker compose down`；保留数据卷以便验证重启持久化。这里的候选人 Compose 开发路径尚待招聘方完整实机验证，与招聘方内部隔离评测路径分别验收。

### 5.2 固定构建与公开脚本

准备阶段下载固定镜像和 Maven 依赖；应用构建使用 `-o` 离线模式。依赖或插件缓存缺失时，先重新准备环境。

若本机已有 Python 3.13.13，也可在应用启动后进入**题目目录 `tasks/ORDER/`**运行公开脚本：

```powershell
python devtools/self_check.py ORDER --url http://127.0.0.1:8080
```

数据库必须使用本题开发专用实例，不连接真实业务数据。

### 5.3 自测覆盖什么

公开脚本检查健康、演示登录、创建、接单、完成，以及读取状态和版本；初始 TODO 尚未实现时，接单步骤失败是预期现象。

你还应自查越权访问、其他角色操作、重复请求、不同备注冲突、多人竞争、数据库恢复与进程重启。脚本可以阅读和扩充，通过它只证明对应流程通过。

## 6. 提交要求

保留原始 `Dockerfile` 和三个 `pom.xml`，提交应用源码、页面资源、配置及实现说明。不要提交 `environment/`、额外依赖清单、安装脚本、第三方库、虚拟环境、归档文件或构建产物。

答案 ZIP 命名为 `姓名_报名手机号_v1.zip`，例如 `张三_13800138000_v1.zip`。使用本人姓名和 11 位报名手机号，由 HR 收件上传。姓名不含下划线；补交时保持姓名和手机号不变，仅递增版本为 `_v2.zip`、`_v3.zip`。系统从文件名读取身份和版本。

```text
张三_13800138000_v1.zip
└── ORDER/
    ├── Dockerfile
    ├── README.md
    ├── pom.xml
    ├── order-api/
    └── order-application/
```

多题提交将所选的 GAME、ORDER、WORKFLOW 工程目录放在 ZIP 根目录同一级，系统按目录识别选题。根目录可附 README.md，不需要额外填写身份或提交清单文件。你交付的 `ORDER/README.md` 写清启动、数据库配置、完成范围、自测命令与实际结果、已知问题、AI 工具和模板／依赖使用情况。

正式评测容器监听 `0.0.0.0:8080`，数据库连接使用运行环境传入的 `MONGO_URI`。运行条件为 Linux amd64、2 CPU／4 GB、非 root 用户、源码只读，临时文件写 `/tmp`。此处规定运行条件，候选人 Compose 的验证边界见第 5.1 节。

按上述目录打包，`devtools/` 无需提交。

## 7. 验收方式与当前边界

客观检查覆盖状态流转、角色与归属、可信价格、幂等、并发竞争、数据库故障一致性、重启持久化，以及原功能保持。检查使用独立数据库，故障与重启由招聘方控制。

| 结果 | 含义 |
|---|---|
| PASS | 已执行的断言通过 |
| FAIL | 行为不符合公开规则 |
| NOT_RUN | 前置能力或环境缺失，未执行或未完成 |
| ERROR | 检查过程异常，需复核 |

报告列出实际检查结果和证据。内部场景可更换本文规则内的输入与故障组合；完整内部用例与答案不分发。未选做不算失败，公开样例通过不代表完整验收通过。

公开自测不操作浏览器，页面功能需自行检查。AI 开发方法结合代码、实现说明与面试交流判断。
