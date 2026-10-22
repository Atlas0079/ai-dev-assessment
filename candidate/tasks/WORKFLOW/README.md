# WORKFLOW｜开发一个订单售后申请助手

## 1. 任务概览

为组织内部的售后处理场景开发一个浏览器助手：理解用户的自然语言诉求，查询其订单与当前政策，补齐必要信息，生成可核对的申请草稿；用户明确点击确认后，向业务服务提交工单，并展示真实返回的工单编号。

需要交付可操作网页、固定 Python 3.13.13／FastAPI 后端及模型接入，使用预装 HTTPX 调用指定服务，可以使用 AI 编码工具；不能用固定关键词分支、硬编码订单或预制成功结果冒充模型处理。

三题全部选做，可只做本题或选择多题。本题使用题包提供的虚构业务服务，可独立完成。

**本文件包含本题全部说明**，依次介绍材料、业务边界、三方接口、配置启动、自测与提交验收。

**模型准备状态：** 指定模型为 `deepseek-v4-pro`，真实服务尚未完成联调，招聘方须在正式发题前确认可用性与运行参数。

## 2. 三个服务的关系

### 2.1 谁提供，谁实现

| 部分 | 责任方 | 本地地址示例 | 作用 |
|---|---|---|---|
| 网页与应用后端 | **你实现** | `http://127.0.0.1:8080` | 会话、消息、草稿、确认、调用模型和业务服务 |
| 虚构业务服务 | **题包提供，你启动** | `http://127.0.0.1:8091` | 校验用户身份，查询订单／政策，实际创建虚构工单 |
| 模型服务 | 按运行配置连接 | 配置中的 `llm.base_url` | 理解语言、组织工具调用与回复 |
| 公开自测 | 题包提供，你运行 | 无常驻端口 | 模拟用户操作，并查询业务服务核对真实工单 |

调用方向是：**浏览器 → 你的应用 → 模型服务／业务服务**。模型返回工具调用意图时，由你的后端执行相应业务请求，再把结果交回模型；模型返回一个函数名不会自动完成 HTTP 调用。

招聘方检查程序同样调用你应用的 `/sessions...` 接口，并在业务服务侧核验实际数据。网页和这些应用接口必须共用业务逻辑。

### 2.2 你需要实现

实现网页、配置加载、会话身份绑定、模型交互、工具执行、草稿管理、明确确认和失败恢复。模型工具的名字与内部代码组织由你决定；第 4 节和第 5 节的 HTTP 路径及字段保持一致。

### 2.3 题包内容

| 路径 | 用途 |
|---|---|
| `README.md` | 本题完整说明 |
| `WORKFLOW/app.py`、`WORKFLOW/Dockerfile` | FastAPI 健康接口和固定构建模板 |
| `WORKFLOW/workflow.config.json` | 运行配置示例，配置加载逻辑需要你实现 |
| `devtools/workflow_support/business.py` | 提供的虚构业务服务 |
| `devtools/workflow_support/self_check.py` | 公开自测 |
| `devtools/Dockerfile`、`compose.yaml` | 业务服务及公开自测的容器配置 |
| `.env.example` | 公开自测的用户令牌与订单号变量示例 |

本题 Compose 启动业务服务；应用按第 7.2 节另行启动在 8080 端口。

## 3. 业务流程与必须遵守的规则

### 3.1 正常申请流程

1. 用户在页面输入业务服务发放的演示令牌，新建会话。
2. 用户描述问题。应用通过模型理解诉求，查询本人订单及政策，必要时继续询问。
3. 信息完整且政策允许时，展示含订单、申请类型和问题描述的草稿。
4. 用户核对草稿后点击明确的确认按钮，应用才请求业务服务创建工单。
5. 应用展示业务服务实际返回的工单编号；仅模型说“已提交”不算完成。

### 3.2 信息与政策

支持 `service_incomplete`（服务未完成）和 `service_quality`（服务质量问题）。草稿需要明确订单、申请类型和非空问题描述，并记录所依据的 `policy_id`。

没有明确订单时必须询问，哪怕查询后只有一张可能符合的订单，也不能自动替用户选择。允许多轮补充，不能只处理一句完整指令。

是否允许申请以业务服务的当前政策为准。公开默认政策允许 `COMPLETED` 订单，不允许 `CANCELLED` 订单；不能把状态规则或订单号写死。政策可能变化，正式测试会使用符合接口的不同数据。

### 3.3 身份与确认

用户身份来自请求头令牌，并通过业务服务核实，不信任用户在文字里声称的身份或请求体中的用户 ID。用户不能访问其他人的会话或订单；订单备注等业务数据不是执行指令，不能据此绕过权限、政策或确认流程。

消息接口绝不创建工单，包括用户发送文字“确认”。只有调用确认接口，才视为明确提交；网页确认按钮对应这个接口。业务服务会检查权限和政策，但它不能代替应用判断用户是否点过确认。未经确认就尝试写入，即使被业务服务拒绝，也不符合要求。

### 3.4 草稿、重复确认和不确定的写入结果

- 待确认阶段收到新消息后，旧草稿失效；生成的新草稿必须有新的 `draft_id`，旧确认请求返回冲突。
- 同会话、同确认 key、同请求体重复提交，返回第一次成功结果；相同 key 换请求体返回 409。
- 即使换一个确认 key，同一草稿也不能重复建单。应用需要为该草稿保留稳定的业务写入 key。
- 如果业务服务已写入，但应用没有收到响应，不能编造成功或直接换 key 重建。应保留待核实状态，用稳定 key 恢复并确认实际结果。
- 结果未核实时可暂时阻止新消息并提示稍后重试；不能清掉待核实状态而产生重复工单。
- 模型或工具不可用时明确呈现原因，有限次尝试后返回，不能无限等待或伪造数据。本题不要求会话跨应用进程重启持久化。

### 3.5 网页要求

页面支持输入用户令牌、新建会话、发送消息、查看草稿、点击确认、查看最终工单编号和失败提示。布局自定，使用原生 HTML、CSS、JavaScript 和本地资源，状态必须对应真实业务结果。

## 4. 你需要实现的应用接口（8080）

### 4.1 通用格式与用户认证

应用监听 `0.0.0.0:8080`，本地可用 `PORT` 覆盖。JSON 使用 UTF-8；成功 HTTP 200 **直接返回对象，不套 `code/data`**。协议错误返回相应 HTTP 状态及 `{"code":"错误标识"}`。

| 方法与路径 | 是否认证 | 用途 |
|---|---|---|
| `GET /` | 否 | 返回网页 |
| `GET /healthz` | 否 | 返回 `{"status":"ok"}` |
| `POST /sessions` | 是 | 创建会话 |
| `POST /sessions/{session_id}/messages` | 是 | 发送消息并推进草稿流程 |
| `POST /sessions/{session_id}/confirm` | 是 | 明确确认当前草稿 |

认证头为 `Authorization: Bearer <虚构业务用户令牌>`。应用创建会话时调用业务服务的 `GET /v1/me` 核实身份，并绑定该用户。无效身份返回 401，跨用户会话返回 403 或 404。

### 4.2 创建会话

```http
POST /sessions
Authorization: Bearer <alice 的业务令牌>
Content-Type: application/json

{}
```

响应示例：

```json
{
  "session_id":"s-实际生成的ID","message":"请说明订单和遇到的问题。",
  "status":"needs_input","draft":null,"ticket":null,"reason_code":null
}
```

### 4.3 发送消息

```http
POST /sessions/<上一步返回的 session_id>/messages
Authorization: Bearer <同一用户的业务令牌>
Content-Type: application/json

{"message":"订单 ORDER-实际编号-A 的服务没有完成，请帮我申请售后。"}
```

满足条件时的响应示例：

```json
{
  "session_id":"s-实际生成的ID",
  "message":"已整理申请，请核对订单和描述后点击确认。",
  "status":"awaiting_confirmation",
  "draft":{
    "draft_id":"d-实际生成的ID","order_id":"ORDER-实际编号-A",
    "request_type":"service_incomplete","description":"用户反映服务没有完成",
    "policy_id":"POLICY-1"
  },
  "ticket":null,"reason_code":null
}
```

三个会话接口使用同一响应结构，字段含义如下：

| 字段 | 含义 |
|---|---|
| `session_id` | 实际会话 ID |
| `message` | 展示给用户的自然语言，不要求逐字匹配 |
| `status` | 下表中的状态，必须反映实际进度 |
| `draft` | 上述五字段草稿对象，无草稿时为 `null` |
| `ticket` | 业务服务返回的工单对象，未成功提交时为 `null` |
| `reason_code` | 拒绝／不可用的原因标识，无原因时为 `null` |

| `status` | 使用时机 |
|---|---|
| `needs_input` | 信息不完整，需要继续询问 |
| `awaiting_confirmation` | 已有当前有效草稿，等待用户点击确认 |
| `completed` | 已确认业务服务实际创建工单 |
| `rejected` | 已确定不满足权限或政策等业务条件 |
| `unavailable` | 模型／工具暂不可用，或写入结果尚不能确认 |

业务拒绝和暂时不可用可以通过上述结构表达，不能返回假 `completed`。参数、身份、草稿冲突等 HTTP 错误见第 4.5 节。

### 4.4 明确确认

```http
POST /sessions/<实际 session_id>/confirm
Authorization: Bearer <同一用户的业务令牌>
Idempotency-Key: confirm-1
Content-Type: application/json

{"draft_id":"当前响应中的 draft_id"}
```

请求体只含 `draft_id`，不能通过此接口另传订单号或修改描述。应用使用自己保存的有效草稿，调用第 5 节的建单接口。成功响应沿用上述结构，`status=completed`，`ticket` 为业务服务实际返回的对象，例如：

```json
{
  "ticket_id":"实际工单ID","user_id":"alice","order_id":"ORDER-实际编号-A",
  "request_type":"service_incomplete","description":"用户反映服务没有完成","status":"OPEN"
}
```

无法确认写入结果时返回 `status=unavailable` 和原因，`ticket=null`，保留同草稿重试的能力。

### 4.5 主要错误

| 情况 | HTTP 状态 |
|---|---|
| 缺少确认 key、请求格式错误 | 400 |
| 无效用户身份 | 401 |
| 访问其他用户会话 | 403 或 404 |
| 未知／过期草稿、同确认 key 换请求体 | 409 |

## 5. 已提供的业务服务接口（8091）

### 5.1 认证与地址

以下接口都由题包提供，**你只需调用，无需实现**。地址取配置的 `business.base_url`，再追加 `/v1/...`。每个请求携带发起会话的业务用户令牌：`Authorization: Bearer <用户令牌>`。

成功 HTTP 200 直接返回 JSON 对象，错误返回对应 HTTP 状态及 `{"code":"错误标识"}`。业务服务不接生产环境。

### 5.2 查询接口

| 方法与路径 | 响应格式 |
|---|---|
| `GET /v1/me` | `{"user_id":"alice"}` |
| `GET /v1/orders` | `{"orders":[订单对象]}`，仅本人订单 |
| `GET /v1/orders/{order_id}` | 一个可见订单对象；他人或不存在的订单返回 404、`ORDER_UNAVAILABLE` |
| `GET /v1/policy` | 当前政策对象 |
| `GET /v1/tickets` | `{"tickets":[工单对象]}`，仅本人工单，可用于核对实际写入 |

订单对象示例：

```json
{"order_id":"ORDER-实际编号-A","owner":"alice","status":"COMPLETED","description":"业务服务中的订单描述"}
```

默认政策对象：

```json
{
  "policy_id":"POLICY-1","allowed_statuses":["COMPLETED"],
  "request_types":["service_incomplete","service_quality"],
  "requires_confirmation":true,"payment_execution":false
}
```

以上 ID 和描述只是示例，使用接口实际返回值。政策含义是当前允许的订单状态、申请类型、是否要求确认及是否涉及付款执行；本题不执行真实付款。

### 5.3 创建工单

```http
POST /v1/tickets
Authorization: Bearer <用户业务令牌>
Idempotency-Key: <应用为该草稿保存的稳定业务写入 key>
Content-Type: application/json

{"order_id":"实际订单ID","request_type":"service_incomplete","description":"核对后的问题描述"}
```

响应为第 4.4 节的工单对象。业务服务按“用户 + key”去重：相同载荷返回原工单，不同载荷返回 409、`IDEMPOTENCY_CONFLICT`。两种 key 的关系如下：

| key | 谁提供 | 作用 |
|---|---|---|
| 确认接口的 `Idempotency-Key` | 网页或检查程序 | 标识本次确认请求，网络重试沿用 |
| 业务建单接口的 `Idempotency-Key` | 你的应用 | 保证同一草稿只建一张工单，用户换确认 key 也不重复建单 |

业务服务还会拒绝无效身份（401）、他人订单（403）、政策不允许（409）、缺少 key 或空描述（400）。这些校验不能替代应用的显式确认。

公开服务不包含评测管理或故障注入接口，应用不得依赖这类能力。正式测试可替换令牌、订单号和政策，调用方式保持一致。

## 6. 模型服务与运行配置

### 6.1 配置文件

应用工程根目录提供 `workflow.config.json`：

```json
{
  "schemaVersion":"1.0",
  "llm":{
    "protocol":"chat_completions","base_url":"https://api.deepseek.com",
    "model":"deepseek-v4-pro","api_key_env":"WORKFLOW_LLM_API_KEY"
  },
  "business":{"base_url":"http://127.0.0.1:8091"},
  "limits":{"max_model_calls_per_message":6,"model_timeout_seconds":45}
}
```

`WORKFLOW_CONFIG_PATH` 有值时，只读取该路径；否则读取工程根目录文件。指定文件缺失、配置无效或密钥缺失时明确失败，不能悄悄回退到另一份个人配置。正式评测会替换地址与凭据，所有运行时调用必须使用生效配置。

模型密钥只从 `api_key_env` 指定的环境变量读取，不写进配置、源码、日志、页面或响应。业务地址去掉尾部斜线后追加 `/v1/...`；模型地址同理追加一次 `/chat/completions`，不要重复拼接。

### 6.2 模型请求约定

应用后端 POST `<llm.base_url>/chat/completions`，携带模型服务的 Bearer API key，使用 Chat Completions 工具调用协议。当前配置约定：

| 参数／限制 | 值 |
|---|---|
| `model` | `deepseek-v4-pro`，真实服务仍待正式联调确认 |
| `thinking` | `{"type":"disabled"}` |
| `stream` | `false` |
| `max_tokens` | `2048` |
| 每条用户消息最大模型调用次数 | 6 |
| 单次模型请求超时 | 45 秒 |
| 单个会话操作最长响应时间 | 300 秒 |

工具定义、工具名及提示词由你实现；工具结果应来自第 5 节业务服务，不能虚构。评测代理会固定上述模型参数，并限制一次评测的模型调用总量为 200 次；若预算或服务导致未完成，应记录原因，不能伪装完成。

一次工具调用的顺序是：应用向模型提交 `messages` 和自己定义的 `tools` → 读取响应 `choices[0].message.tool_calls` → 按 `function.name` 分派，并解析 JSON 字符串 `function.arguments` → 用当前会话绑定的用户令牌请求业务服务 → 把真实结果作为 `role=tool`、带对应 `tool_call_id` 的消息交回模型。工具参数不能覆盖可信用户身份。模型可辅助整理草稿，但消息处理阶段不能执行建单；建单由确认接口控制。

### 6.3 不同凭据不要混用

| 凭据 | 来源 | 发送到哪里 |
|---|---|---|
| alice／bob 用户令牌 | 本地业务服务启动输出 | 网页→应用；应用→业务服务 |
| 模型 API key | 开发或正式评测环境 | 仅应用后端→配置的模型服务 |

用户令牌不是模型密钥。网页不应收到模型密钥。候选人不需要招聘方内部评测控制令牌。

当前方案中，开发时使用自己的模型凭据并承担相关调用费用；正式评测使用招聘方凭据，不要求提交个人 key。如需其他费用安排，发题前与联系人确认。开发可使用其他兼容模型，真实服务准备完成后仍需在指定模型上试测。不能依赖个人云工作流或额外收费服务才能运行交付应用；AI 编码工具不受此运行时限制。

## 7. 启动与自测

### 7.1 第一步：启动题包业务服务

本题使用总题包 `environment/` 中的固定环境。首次开发前，在当前 `tasks/WORKFLOW/` 目录运行 `python ../../environment/fixed_runtime.py prepare`，准备过程需要 Docker、网络和磁盘；准备成功后再启动本题。环境说明和完整依赖清单见 [总包说明](../../README.md) 与 [固定依赖](../../environment/requirements.lock)。

使用题包提供的库及语言标准库，不新增或升级依赖。前端使用原生 HTML、CSS、JavaScript，资源随源码提交。保留原始 `Dockerfile`。

命令起点为**题目目录**；总题包先进入 `tasks/WORKFLOW/`。

有 Docker 时：

```powershell
docker compose up -d --build business
docker compose logs business
```

或者使用 Python 3.13.13，从**题目目录 `tasks/WORKFLOW/`**进入 `devtools/`：

```powershell
cd devtools
python -m workflow_support.business --port 8091
```

两种方式选一种。保留服务运行，启动输出含 alice／bob 的令牌和三个订单号：alice 的已完成订单、bob 的已完成订单、alice 的已取消订单。数据在内存，每次重启令牌和订单号都会变化，已有工单也会清空。

### 7.2 第二步：配置并启动你的应用

在另一个终端进入**应用工程目录 `tasks/WORKFLOW/WORKFLOW/`**。按第 6 节实现并设置配置与密钥，再用固定 Python 环境启动应用。本机调试需在独立虚拟环境按总包 requirements.lock 安装全部固定依赖；启动命令：

```powershell
$env:WORKFLOW_LLM_API_KEY='你的开发模型密钥'
$env:WORKFLOW_CONFIG_PATH=(Join-Path (Get-Location).Path 'workflow.config.json')
python app.py
```

骨架仅提供健康接口和占位页面，配置读取与会话功能需实现。模型密钥不要写入交付文件。

宿主机运行应用时，业务地址为 `http://127.0.0.1:8091`。若应用运行在容器内，`127.0.0.1` 指向该容器，需改为从该容器可达的业务服务地址；例如把应用加入业务服务所在 Compose 网络后使用 `http://business:8091`。默认题包 Compose 不包含应用服务。

### 7.3 第三步：从页面走一遍

访问 `http://127.0.0.1:8080/`，输入业务服务实际输出的 alice 令牌，新建会话，使用 alice 已完成订单号提出申请。核对草稿，确认前不能有工单；点击确认后看到实际工单编号。

另行检查缺少订单、多轮补充、他人订单、取消订单、修改草稿后旧确认失效、重复确认，以及模型不可用时的提示。

### 7.4 第四步：运行公开自动自测

保持业务服务和应用运行。Python 方式：在新终端进入 **`tasks/WORKFLOW/devtools/`**，设置实际令牌并替换实际订单号：

```powershell
$env:WORKFLOW_USER_TOKEN='业务服务输出的 alice 令牌'
python -m workflow_support.self_check --url http://127.0.0.1:8080 --business-url http://127.0.0.1:8091 --order ORDER-实际编号-A
```

若业务服务由 Compose 启动、你的应用在宿主机 8080 运行，也可在**题目目录 `tasks/WORKFLOW/`**执行：

```powershell
$env:WORKFLOW_USER_TOKEN='业务服务输出的 alice 令牌'
$env:WORKFLOW_ORDER_ID='业务服务输出的 alice 已完成订单号'
docker compose --profile check run --rm public-check
```

自测会消耗模型额度并创建虚构工单，检查草稿、明确确认和重复确认流程。真实模型与替身验证结果须分别记录。

### 7.5 停止服务

在**题目目录 `tasks/WORKFLOW/`**用 `docker compose down` 停止 Compose 业务服务；直接启动的业务服务和应用分别在各自终端停止。这里的候选人 Compose 开发路径尚待招聘方完整实机验证，与招聘方内部隔离评测路径分别验收。

## 8. 提交要求

保留原始 `Dockerfile`，提交应用源码、页面资源、配置及实现说明。启动入口固定为 `app.py`，可自行增加内部模块。不要提交 `environment/`、额外依赖清单、安装脚本、第三方库、虚拟环境、归档文件或构建产物。

答案 ZIP 命名为 `姓名_报名手机号_v1.zip`，例如 `张三_13800138000_v1.zip`。使用本人姓名和 11 位报名手机号，由 HR 收件上传。姓名不含下划线；补交时保持姓名和手机号不变，仅递增版本为 `_v2.zip`、`_v3.zip`。系统从文件名读取身份和版本。

```text
张三_13800138000_v1.zip
└── WORKFLOW/
    ├── Dockerfile
    ├── README.md
    ├── workflow.config.json
    └── 应用源码和本地页面资源
```

多题提交将所选的 GAME、ORDER、WORKFLOW 工程目录放在 ZIP 根目录同一级，系统按目录识别选题。根目录可附 README.md，不需要额外填写身份或提交清单文件。应用运行时连接配置指定的业务服务，不把 `devtools/` 当成应用答案提交。

你交付的 `WORKFLOW/README.md` 写清构建启动、配置加载、依赖、完成范围、自测步骤与真实结果、已知问题、AI 工具和模板／依赖使用情况。分别说明真实模型执行与开发中使用的替身验证，不能混称已通过。

正式评测容器监听 `0.0.0.0:8080`，支持只读挂载的 `WORKFLOW_CONFIG_PATH` 与环境变量凭据。运行条件为 Linux amd64、2 CPU／4 GB、非 root 用户、源码只读，临时文件写 `/tmp`；正式运行仅连接指定模型与业务服务。运行条件与真实模型能力分别验收，模型联调状态见第 1 节，候选人 Compose 的验证边界见第 7.5 节。

按上述目录打包，不提交模型密钥或测试替身。

## 9. 验收方式与当前边界

客观检查关注订单与政策依据、多轮补充、身份权限、明确确认、草稿更新、重复请求、异常恢复及模型接入。内部测试可更换本文规则内的数据、表达和故障组合；完整用例和答案不随题包提供。

| 结果 | 含义 |
|---|---|
| PASS | 已执行的断言通过 |
| FAIL | 实际行为不符合公开规则 |
| NOT_RUN | 前置能力、环境或调用预算不足，未执行或未完成 |
| ERROR | 检查过程异常，需复核 |

报告列出实际检查结果和证据。未选做不算失败，公开自测通过不代表完整验收通过；未执行真实模型时如实注明。

公开自测不操作浏览器，页面流程需按第 7.3 节自行检查。
