# GAME｜开发一个浏览器多人纸牌游戏

## 1. 任务概览

为社交平台开发一个 2—4 人在线玩的 UNO 简化版游戏。交付可操作的网页和实际运行的游戏服务，让不同浏览器中的玩家完成建房、加入、准备、开局、轮流出牌或摸牌，直到产生胜者。

使用固定 Python 3.13.13、FastAPI、Uvicorn、HTTPX 环境和原生网页，可以使用熟悉的 AI 编码工具；本题不要求游戏接入大模型。

三题全部选做，可只做本题，也可选择多题。

**本文件包含本题全部说明**，依次介绍材料、规则、接口、启动自测及提交验收。`samples/` 中的 JSON 文件为配套数据。

## 2. 已提供的材料与开发范围

### 2.1 题包里有什么

| 路径 | 已提供内容 | 你需要做什么 |
|---|---|---|
| `README.md` | 本题完整说明 | 按本文实现与自测 |
| `GAME/app.py`、`GAME/Dockerfile` | FastAPI 健康检查骨架和固定构建模板 | 在固定环境内实现游戏 |
| `samples/fixture.json`、`samples/fixture.schema.json` | 固定牌局样例与结构定义 | 调试测试接口，完成数据校验 |
| `devtools/` | 公开自测脚本 | 对运行中的应用执行自测 |
| `compose.yaml` | 应用启动、自测配置 | 使用题包原始配置 |

初始工程只实现 `/healthz`，直接运行公开自测时，游戏步骤失败是预期现象。

### 2.2 谁实现接口，谁调用接口

| 部分 | 实现方 | 调用方 | 用途 |
|---|---|---|---|
| 网页 `/` | 你 | 玩家浏览器 | 操作游戏、显示状态 |
| 普通游戏接口 `/v1/...` | 你 | 你的网页、自动检查程序 | 建房、开局、读取牌局、执行动作 |
| 测试接口 `/__test/...` | 你 | 本地调试工具、招聘方检查程序 | 设置固定牌局，读取完整状态核对规则 |
| 公开自测脚本 | 题包提供 | 你在终端运行 | 请求你的服务，检查基本流程 |

三类 HTTP 路径属于**同一个候选人应用**，默认监听 `0.0.0.0:8080`。没有另一台替你实现规则的游戏服务。测试接口也需要你实现，且必须操作普通接口使用的同一份状态和规则引擎。

普通玩家使用 `playerToken`；测试程序使用 `EVAL_CONTROL_TOKEN`。普通玩家不能通过测试接口读取完整牌局。

## 3. 业务规则与网页要求

### 3.1 牌与正常开局

| 牌型 | 组成 | 数量 |
|---|---|---|
| 数字牌 | 红 R、黄 Y、蓝 B、绿 G，每色 0—9 各一张 | 40 |
| 功能牌 | 每色 SKIP、REVERSE、DRAW2 各一张 | 12 |
| 万能牌 | WILD，颜色记为 W | 8 |

共 60 张牌，不包含 +4、喊 UNO 或相应罚牌规则。

房间容纳 2—4 人，房主也是玩家，座位按加入顺序排列。人数满足且所有玩家准备后，由房主开局；开局后不能再加入。每人发 7 张，初始弃牌顶取剩余牌库中遇到的第一张数字牌，遇到的非数字牌放回牌库底。初始方向沿座位顺序，由房主先行动。

### 3.2 每回合的动作与胜负

轮到自己时，可打出与当前颜色或弃牌顶 `value` 相同的牌，或打出 WILD 并指定下一颜色。也可主动摸一张，即使手中有能出的牌；摸牌后立即结束回合，不允许再打出刚摸的牌。

| 动作／牌型 | 效果 |
|---|---|
| 数字牌 | 下一位行动 |
| SKIP | 跳过下一位 |
| REVERSE | 反转方向；两人局等同跳过对方 |
| DRAW2 | 下一位摸两张并被跳过，不允许叠加 |
| WILD | 出牌者指定 R／Y／B／G，再交给下一位 |
| DRAW 动作 | 当前玩家摸一张，交给下一位 |

需要摸牌而牌库不足时，保留弃牌顶，将其他弃牌洗回牌库。仍不足则只摸到实际可用的牌，随后正常结束回合；DRAW2 同样适用。不能复制或丢失牌，洗牌算法不限。

玩家打完最后一张牌即获胜；如果是功能牌，先执行效果，再设为 `FINISHED`。结束后拒绝新动作。`currentPlayerId` 保留最后动作计算出的下一位玩家，即使牌局已经结束。

### 3.3 状态、并发与重复请求

- 成功动作使 `revision` 恰好增加 1；非法动作不能改变完整状态。
- 客户端提交自己看到的 `expectedRevision`；同版本并发动作最多一个成功。
- 同玩家、同对局、同 `requestId`、相同请求体的成功请求，重试返回首次响应，不再次执行。相同 `requestId` 换请求体返回 409。
- 成功请求的重放判断先于回合、版本、终态检查，不能因为首次执行已推进回合就拒绝合法重试。
- ready/start 按玩家、房间、操作、`requestId` 幂等；ready 重放返回首次准备状态快照。

### 3.4 网页操作与多人同步

网页支持创建／加入房间、准备、开局、查看本人手牌和他人牌数、出牌、摸牌、万能牌选色及显示胜者。其他浏览器应在 3 秒内看到状态变化。

刷新后恢复玩家身份和房间。断线玩家保留座位，轮到他时等待恢复，不自动代打。本题不要求服务进程重启后恢复牌局。

页面布局与同步方式自定，前端使用原生 HTML、CSS、JavaScript，不规定元素 ID、浏览器存储键名或提示文案。网页通过普通接口操作游戏，不应持有测试控制令牌。

## 4. 普通游戏接口

### 4.1 通用格式与身份

JSON 使用 UTF-8，请求头为 `Content-Type: application/json`。成功返回 HTTP 200 和对象，也允许统一包装为 `{"code":0,"data":对象}`。下面示例采用直接对象格式。健康接口直接返回 `{"status":"ok"}`，可附加运行信息。错误返回实际 HTTP 错误状态及 `{"code":"错误标识"}`。

**创建、加入房间不需要令牌**，响应中的 `playerToken` 是后续操作凭据。其余玩家接口携带 `Authorization: Bearer <playerToken>`。不能根据请求体中的 `playerId` 授权。令牌绑定具体房间／对局，不同对局即使玩家 ID 相同也不能交叉访问。

`requestId` 为非空字符串；新操作使用新值，重试同一操作沿用原值和原请求体。示例中的房间、玩家、令牌、牌局 ID 均为占位示例，以实际响应为准。

### 4.2 房间接口

| 方法与路径 | 请求体 | HTTP 200 响应 |
|---|---|---|
| `GET /healthz` | 无 | `{"status":"ok"}` |
| `POST /v1/rooms` | `{"displayName":"A"}` | `{"roomId":"r1","playerId":"p1","playerToken":"token-A"}` |
| `POST /v1/rooms/{roomId}/join` | `{"displayName":"B"}` | 同上，返回加入者自己的 ID 与令牌 |
| `GET /v1/rooms/{roomId}` | 无 | 房间状态，见下例 |
| `POST /v1/rooms/{roomId}/ready` | `{"ready":true,"requestId":"ready-A-1"}` | `{"ready":{"p1":true}}`，准备状态映射 |
| `POST /v1/rooms/{roomId}/start` | `{"requestId":"start-1"}` | 第 4.3 节的公开牌局对象 |

两人准备后的房间示例：

```json
{"players":["p1","p2"],"ready":{"p1":true,"p2":true},"host":"p1","gameId":null}
```

`players` 为座位顺序的玩家 ID 数组，`ready` 为 ID 到布尔值的映射，`host` 为房主 ID；`gameId` 开局前为 `null`，开局后为实际牌局 ID。

### 4.3 读取牌局、出牌与摸牌

| 方法与路径 | 输入 | HTTP 200 响应 |
|---|---|---|
| `GET /v1/games/{gameId}` | 无请求体 | 请求者可见的公开牌局对象 |
| `POST /v1/games/{gameId}/actions` | 下列动作对象 | 动作完成后请求者可见的公开牌局对象 |

普通牌 PLAY：

```json
{"requestId":"play-1","expectedRevision":0,"type":"PLAY","cardId":"a"}
```

WILD PLAY：

```json
{"requestId":"wild-1","expectedRevision":0,"type":"PLAY","cardId":"wild-a","chosenColor":"B"}
```

DRAW：

```json
{"requestId":"draw-1","expectedRevision":0,"type":"DRAW"}
```

`expectedRevision` 为非负整数，不接受布尔值。PLAY 必填 `cardId`，WILD 另需合法 `chosenColor`；DRAW 不需要 `cardId`，即使携带也忽略该字段。

公开牌局对象只含以下字段。此处是缩小场景，正常开局仍须按 60 张牌发牌：

```json
{
  "gameId":"g1","currentPlayerId":"A","direction":1,"currentColor":"R",
  "revision":0,"status":"PLAYING","winnerId":null,
  "hand":[{"cardId":"a","color":"R","value":"1"}],
  "players":[{"playerId":"A","count":1},{"playerId":"B","count":1}],
  "top":{"cardId":"top","color":"R","value":"3"},"drawCount":0
}
```

`hand` 只含本人的牌；`players` 按座位顺序只含 ID 和牌数；`top` 为弃牌顶；`drawCount` 为牌库张数。不额外返回调试状态、他人手牌或未知牌库的 ID、牌面、顺序。摸到的牌追加在手牌末尾，出牌后其余手牌保持原顺序。

### 4.4 正常玩家的一次完整调用顺序

1. A 建房，保存 `roomId` 和自己的 ID、令牌。
2. B 使用该 `roomId` 加入，保存自己的 ID、令牌。
3. A、B 分别用自己的令牌 ready；A 用房主令牌 start。
4. start 返回 `gameId`，双方分别 GET 牌局，看到各自的手牌。
5. 当前玩家带最新版本提交动作，其他玩家刷新状态，继续下一回合。
6. 网络重试沿用原请求；版本冲突后重新读取状态，再决定新操作。

整个正常流程不需要控制令牌，也不调用测试接口。

## 5. 测试接口与固定牌局

### 5.1 开启方式与权限

随机开局难以稳定复现边界。测试接口用于设置明确的初始状态，再由普通接口执行动作，最后核对真实状态变化，不能返回预制测试答案。

应用启动时读取 `EVAL_FIXTURES` 和 `EVAL_CONTROL_TOKEN`。仅在 `EVAL_FIXTURES=1` 且控制令牌非空时开启；两个测试接口都要求 `Authorization: Bearer <EVAL_CONTROL_TOKEN 的值>`。

测试模式关闭返回 404；开启但令牌缺失、错误或为普通玩家令牌时返回 401 或 403。

### 5.2 接口定义

| 方法与路径 | 输入 | HTTP 200 响应 |
|---|---|---|
| `POST /__test/fixtures` | 第 5.3 节的固定牌局 | `{"gameId":"新ID","tokens":{"A":"token-A","B":"token-B","C":"token-C"}}` |
| `GET /__test/games/{gameId}` | 无请求体 | 同固定牌局格式的当前完整状态，另加 `gameId` |

每次注入新建独立牌局，不覆盖其他牌局；`tokens` 覆盖所有输入玩家。注入直接进入 `PLAYING`，不需再建房或准备。完整状态读取不改变状态，不返回令牌、内部幂等记录等额外字段；不存在的牌局返回 404。

### 5.3 固定牌局的全部字段

下面与 `samples/fixture.json` 一致，可直接作为注入请求体：

```json
{
  "schemaVersion":"1.0",
  "players":[
    {"id":"A","hand":[{"cardId":"play","color":"R","value":"1"},{"cardId":"extra","color":"B","value":"9"}]},
    {"id":"B","hand":[{"cardId":"B","color":"G","value":"4"}]},
    {"id":"C","hand":[{"cardId":"C","color":"G","value":"4"}]}
  ],
  "drawPile":[{"cardId":"d1","color":"Y","value":"2"},{"cardId":"d2","color":"B","value":"3"}],
  "discardPile":[{"cardId":"top","color":"R","value":"1"}],
  "currentPlayerId":"A","direction":1,"currentColor":"R",
  "revision":0,"status":"PLAYING","winnerId":null
}
```

| 字段 | 类型与约束 |
|---|---|
| `schemaVersion` | 固定字符串 `"1.0"` |
| `players` | 2—4 人的有序数组，每项为 `id` 和 `hand`；ID 为局内唯一非空字符串；注入时每人至少一张牌 |
| `drawPile` | Card 数组，索引 0 先抽取，可为空 |
| `discardPile` | 非空 Card 数组，末尾为弃牌顶 |
| `currentPlayerId` | 必须属于 `players` |
| `direction` | 整数 1 或 -1，不接受布尔值 |
| `currentColor` | R／Y／B／G；非 WILD 顶牌时等于顶牌颜色 |
| `revision` | 非负整数，不接受布尔值 |
| `status` | 注入时 `PLAYING`；运行后为 `PLAYING` 或 `FINISHED` |
| `winnerId` | 注入时 `null`，结束后为胜者 ID |

Card 仅含 `cardId`、`color`、`value`。`cardId` 为非空字符串，在所有位置全局唯一，同一张牌不能同时位于手牌和牌库等多处。数字 `value` 为字符串 `"0"`—`"9"`；普通功能牌为 `SKIP`／`REVERSE`／`DRAW2`，颜色为 R／Y／B／G；WILD 的颜色为 W。

固定场景不要求凑齐 60 张，也不检查是否能从真实随机开局推演得到；不同 ID 可以使用相同合法牌面。Schema 表达结构，ID 唯一性和跨字段关系仍需业务校验。

### 5.4 用样例检查一次动作

1. 用控制令牌 POST 上述样例，取得 `gameId` 和 `tokens.A`。
2. 用控制令牌读取完整状态，核对注入内容。
3. 用 `tokens.A` 请求普通 actions 接口：`{"requestId":"sample-play-1","expectedRevision":0,"type":"PLAY","cardId":"play"}`。
4. 再读完整状态：A 只剩 `extra`，弃牌顶为 `play`，轮到 B，`revision=1`，牌库不变。
5. 原样重放第 3 步，返回首次响应，状态不再次变化。

## 6. 错误响应

| 情况 | HTTP 状态 |
|---|---|
| 非法固定牌局、缺少／错误万能颜色、未知动作、字段类型错误 | 400 |
| 无效玩家令牌 | 401 |
| 非成员、跨局访问、非房主开局、非当前玩家操作 | 403 |
| 资源不存在、测试模式关闭 | 404 |
| 不匹配或不持有的牌、版本过期、幂等冲突、终态操作、人数／准备／加入限制 | 409 |

并发动作失败方同时涉及回合及版本冲突时接受 403 或 409。错误体例如 `{"code":"STALE_REVISION"}`，应能解释原因；不要求提示文案逐字匹配。检查会核对 HTTP 状态和拒绝后状态不变。

## 7. 启动与自测

### 7.1 启动应用

本题使用总题包 `environment/` 中的固定环境。首次开发前，在当前 `tasks/GAME/` 目录运行 `python ../../environment/fixed_runtime.py prepare`，准备过程需要 Docker、网络和磁盘；准备成功后再启动本题。环境说明和完整依赖清单见 [总包说明](../../README.md) 与 [固定依赖](../../environment/requirements.lock)。

只能使用题包提供的库及语言标准库，禁止新增、升级依赖，禁止额外安装脚本、依赖包、外部 CDN 或个人常驻服务。前端使用原生 HTML、CSS、JavaScript，资源随源码提交。可以自由使用 AI 编码工具。`Dockerfile` 是受保护的原文件，提交时保留且不能修改；正式评测使用服务端固定模板。


以下命令在**题目目录**运行；总题包先进入 `tasks/GAME/`。

Docker 方式：

```powershell
docker compose up -d --build
docker compose logs app
```

本机调试须使用 Python 3.13.13，并在独立虚拟环境按总包 requirements.lock 安装全部固定依赖，再运行骨架：

```powershell
python GAME/app.py
```

健康检查为 `http://127.0.0.1:8080/healthz`，网页为 `http://127.0.0.1:8080/`。骨架只有健康接口，需完成后才能玩游戏。启动入口固定为 app.py，不能替换语言或自行安装其他库。

### 7.2 公开自动自测

保持应用运行，在另一个终端进入**题目目录 `tasks/GAME/`**，任选一种方式：

```powershell
docker compose --profile check run --rm public-check
```

或使用 Python 3.13.13：

```powershell
python devtools/self_check.py GAME --url http://127.0.0.1:8080
```

自测检查健康接口、两人建房／加入／准备／开局，以及房主摸牌后的手牌增加和回合推进。它不需要测试控制令牌，也不覆盖完整规则；脚本可阅读，可自行增加测试。

### 7.3 测试接口与浏览器自测

在**题目目录 `tasks/GAME/`** 的终端设置变量后，再启动应用：

```powershell
$env:EVAL_FIXTURES='1'
$env:EVAL_CONTROL_TOKEN='local-only-test-token'
python GAME/app.py
```

容器方式需把变量传入应用容器，默认 Compose 没有开启测试模式。执行第 5.4 节流程，再关闭测试模式核对 404。

用不同浏览器或独立会话检查隐私、同步、刷新恢复和完整对局。公开自动脚本不操作浏览器，不能据此认定页面要求已通过。

Compose 应用用 `docker compose down` 停止；直接启动的进程在相应终端停止。这里的候选人 Compose 开发路径尚待招聘方完整实机验证，与招聘方内部隔离评测路径分别验收。

## 8. 提交要求

保留题包原始 `Dockerfile`。除固定配置外，只提交应用源码、页面资源、配置及实现说明；不要提交 `environment/`、额外依赖清单、安装脚本、第三方库源码／二进制、虚拟环境、归档文件或构建产物。Python 应用固定从 `app.py` 启动；内部模块可自行增加。源码与依赖声明检查会指出明确违规，但不能据此证明不存在动态加载或内嵌第三方代码。

答案 ZIP 命名为 `姓名_报名手机号_v1.zip`，例如 `张三_13800138000_v1.zip`。使用本人姓名和 11 位报名手机号，由 HR 收件上传。姓名不含下划线；补交时保持姓名和手机号不变，仅递增版本为 `_v2.zip`、`_v3.zip`。系统从文件名读取身份和版本。

```text
张三_13800138000_v1.zip
└── GAME/
    ├── Dockerfile
    ├── README.md
    └── 应用源码和本地页面资源
```

多题提交将所选的 GAME、ORDER、WORKFLOW 工程目录放在 ZIP 根目录同一级，系统按目录识别选题。根目录可附 README.md，不需要额外填写身份或提交清单文件。

你交付的 `GAME/README.md` 是实现说明，写清构建启动、环境变量、完成范围、自测命令与实际结果、已知问题、AI 工具和模板／依赖的使用情况。

正式评测容器监听 `0.0.0.0:8080`，运行条件为 Linux amd64、2 CPU／4 GB、非 root 用户、源码只读，临时文件写 `/tmp`。此处规定运行条件，候选人 Compose 的验证边界见第 7.3 节。

不要多套目录，题包 `devtools/` 无需提交。

## 9. 验收方式与当前边界

客观检查覆盖正常开局、牌与回合规则、胜负、手牌隐私、非法动作、重复和并发请求、状态一致性。内部测试可更换本文规则内的牌局和操作组合；完整内部用例与答案不随题包提供。

| 结果 | 含义 |
|---|---|
| PASS | 已执行的断言通过 |
| FAIL | 实际行为与预期不符 |
| NOT_RUN | 前置能力或环境缺失，未执行或未完成 |
| ERROR | 检查过程异常，需复核 |

报告优先列出未通过用例、实际观察和证据，分别列出未执行、异常和已通过范围。未选做不算失败，通过公开样例不代表完整验收通过。

当前没有自动浏览器验收，页面操作、3 秒同步和刷新恢复需人工体验或后续浏览器测试。AI 开发方法需结合代码、实现说明与面试交流判断。

架构、美观等主观评价暂未启用，LLM 建议留空，未来可独立增加。当前不生成分数或录用结论。
