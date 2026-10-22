# AI 全栈开发｜选题目录

题目全部选做。每题只有一份完整业务说明，包含任务、材料、接口、启动自测、提交和验收信息；通用环境在本文准备。

- [GAME｜多人 UNO 简化版](tasks/GAME/README.md)（平台内社交小游戏）
- [ORDER｜接手模拟订单服务](tasks/ORDER/README.md)（社交平台开发）
- [WORKFLOW｜订单售后申请助手](tasks/WORKFLOW/README.md)（组织内部员工提效）

最多两天由 HR 软性约定，系统不计时。当前不评分，直接提供用例结果与证据，主观评价暂未启用。

选择题目后进入对应 `tasks/<题目>/` 目录，按其中 README.md 操作。答案 ZIP 统一命名为 `姓名_报名手机号_v1.zip`，例如 `张三_13800138000_v1.zip`；使用本人姓名和 11 位报名手机号，补交时保持姓名、手机号不变并递增为 `_v2.zip`。系统从文件名读取身份和提交版本，从 ZIP 根目录的 GAME、ORDER、WORKFLOW 工程识别选做题目。完整提交布局见每题说明。

## 目录起点

| 本文和题面中的称呼 | 解压总包后的路径 | 用途 |
|---|---|---|
| 总包根目录 | 含本 README、environment/ 与 tasks/ 的目录 | 准备环境、安装本机调试依赖 |
| 题目目录 | tasks/GAME/、tasks/ORDER/、tasks/WORKFLOW/ | 阅读题面、运行 Compose 与公开自测 |
| 应用工程目录 | tasks/GAME/GAME/、tasks/ORDER/ORDER/、tasks/WORKFLOW/WORKFLOW/ | 编写应用；提交时将所选工程直接放在答案 ZIP 根目录 |

题面中的命令按各节注明的目录执行；切换终端后也需先进入对应目录。发题包的 environment/、tasks/ 外层和 devtools/ 不作为应用答案提交。

## 固定开发环境

所有题目使用 Linux amd64 容器、8080 应用端口和题包原始构建配置。GAME／WORKFLOW 为 Python 3.13.13、FastAPI 0.156.4、Uvicorn 0.54.0、HTTPX 0.28.1；所有间接依赖的精确版本及安装包 SHA-256 在 [requirements.lock](environment/requirements.lock)。Maven 的全部 559 个 POM／JAR 文件也按内容哈希锁定在 [maven-artifacts.lock](environment/maven-artifacts.lock)，准备镜像时逐项核对文件集合与摘要，避免版本范围或仓库变化悄悄引入其他库。ORDER 保留 Java 8、Maven 3.9.9、Spring Boot 2.1.13.RELEASE 与现有依赖，MongoDB 为 7.0.16。基础镜像按 Linux amd64 镜像摘要固定，见 [runtime.json](environment/runtime.json)。

首次解压总题包后，在总包根目录运行：

```powershell
python environment/fixed_runtime.py prepare
```

需要 Python 3.13、可运行 Linux 容器的 Docker，以及准备阶段的镜像／依赖下载网络。此命令先准备固定 Python 镜像和 Maven 构建缓存，再实际执行离线构建与 Python Web 健康检查；全部成功后才写入本机准备标记。完成后进入 `tasks/<题目>/`，按题面启动。可运行 `python environment/fixed_runtime.py verify` 检查本机环境版本和镜像身份。环境源码、锁文件或固定配置变更后须重新准备；不要把一台机器的准备标记复制到另一台。

Python 应用也可在本机独立虚拟环境调试，需 Python 3.13.13。在总包根目录执行以下 PowerShell 命令，激活后再进入对应工程运行 app.py：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r environment/requirements.lock
```

Linux 激活命令改为 `source .venv/bin/activate`。正式检查以提供的 Linux 容器为准。不得修改锁文件、Dockerfile 或 ORDER 的三个 pom.xml，不得安装新库、升级版本、增加服务或使用外部 CDN。允许自行编写业务模块；不允许复制第三方库源码或携带其二进制。AI 编码工具自由使用。

评测使用服务端原始模板，构建时关闭下载网络；缺少我们承诺提供的依赖属于平台事项，新增依赖或改动受保护配置属于提交规范问题。静态检查覆盖明确的依赖声明、Python 导入、常见外链资源及禁止的材料，不能证明不存在动态加载或隐蔽嵌入的第三方代码。
