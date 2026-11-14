# Epic 角色属性分析测试包

本包使用官方 `v1113-pr13-epic-test` 的 Epic 原生宿主，加入当前分支的角色属性分析、双榜候选、推荐分级、报告和启动器子进程清理功能。Steam 与 Epic 使用不同的适配器，请勿混用。

目标环境为 Windows x64、完整的 Epic FM27 27.0.1 安装。目标 `fm_Data/Plugins/x86_64/game_plugin.dll` SHA256：

```text
ebf6fcf57f554dc7178fb2afa4e1fd4d6e6dcb693f65a1a11216abb8d00c8396
```

## 构建

从官方 Releases 下载 Epic 测试版 EXE，然后在仓库根目录执行：

```powershell
python scripts/repackage_release.py --platform epic --release-exe "官方Epic测试版.exe" --output "dist/FM27-Tactics-Lab-v1113.1-Epic-Role-Attribute-Research-Test.exe"
```

脚本分别核验官方 EXE、资源包和 Epic 引擎参考标识，并使用 `EPIC_BUILD` 编译启动器。生成的 `.build.json` 记录来源及二进制指纹。该流程复用官方原生宿主，不声称重新编译了本分支 native 改动。

普通使用者运行 EXE 不需要安装 Python。首次启动手动选择 Epic 游戏根目录。正常数据目录为当前用户的 `FM27TacticsDesktop_PR13_Epic`，与 Steam 分开。“战术执行力实验”在当前 Epic 构建上不受支持，应保持关闭；角色属性分析是独立功能。

## 实机验收

测试脚本需要 Python，可在包含源码的电脑上执行：

```powershell
python scripts/acceptance_epic.py --exe "dist/FM27-Tactics-Lab-v1113.1-Epic-Role-Attribute-Research-Test.exe" --game-root "Epic游戏安装目录"
```

脚本先检查游戏版本和原生兼容性，然后在独立临时数据目录中执行：

1. 一场完整原生比赛。
2. 两阶段角色属性分析。
3. 探索阶段取消续跑、切入验证阶段后的取消续跑；核对已完成场次保留且无重复。
4. 在批量比赛运行中正常退出与强制结束测试启动器，检查其已捕获子进程均退出。

脚本输出 `acceptance.json` 和日志路径。只有全部通过时状态为 `passed`；缺少匹配游戏为 `blocked`，运行或断言失败为 `failed`。如果本次探索没有产生正向候选，验证阶段无法覆盖，脚本会失败并要求另选实验样本，不会跳过后宣称全部通过。

## 当前验证范围

已完成独立 Epic 包构建和启动自检；自检只证明自带 Python、服务与界面资源可启动，未执行 Epic 原生比赛。开发机没有 Epic FM27 安装，以上 Epic 原生验收仍待执行。不能将 Steam 测试或启动自检视为 Epic 比赛验证。

### 无 Epic 安装的后台验证

| 检查 | 已验证内容 | 不代表什么 |
| --- | --- | --- |
| 包来源与内容 | 官方 Epic EXE、内嵌资源、目标 DLL 标识校验；包内属性分析源码与当前源码一致 | 不代表游戏能完成比赛 |
| Epic 包启动自检 | 自带 Python、HTTP 服务、界面资源可启动并退出，无测试进程残留 | 没有载入 Epic 游戏引擎 |
| Epic 宿主能力查询 | protocol 2、百万任务上限、执行上下文重置与逐场资源释放声明可读取 | 能力声明不等于长实验实测 |
| 错误平台检查 | 本机 Steam DLL 被 Epic 宿主以 `epic_build_fingerprint_mismatch` 拒绝，退出码 99 | 未验证正确 Epic DLL 能通过 |
| Epic 启动器进程树 | 实际 `EPIC_BUILD` 启动器配合合成服务；正常退出和强制结束均清理 4 个进程（启动器、服务、子进程、孙进程） | 没有验证 Epic 原生 SDK 的退出行为 |
| Steam 上共用流程回归 | 一场完整比赛、44/44 场两阶段属性实验；探索完成 2 场及切入验证完成 20 场时分别取消续跑，已完成结果保留且无重复；运行中正常退出和强制结束均清理捕获的 11 个相关进程 | 这是 Steam 平台结果，不是 Epic 引擎验收 |
| 单元和界面测试 | 180 项 Python 测试中 176 项通过、4 项跳过；报告和中英文界面测试通过 | 不代表跨机器或游戏引擎结果准确 |

启动器进程树测试可复现：

```powershell
python scripts/check_epic_launcher.py --official-epic-exe "官方Epic测试版.exe"
```

该脚本使用明确标记的合成服务和休眠子进程，不产生虚构比赛结果，不改动正式 EXE。报告含 `synthetic_process_tree` 和 `epic_native_match_verified: false`。

共用流程可在 Steam 安装上回归，报告必须标记 `platform: steam`：

```powershell
python scripts/acceptance_epic.py --platform steam --exe "Steam功能测试包.exe" --game-root "Steam游戏安装目录"
```

### 静态适配审查发现

- 属性实验构造、同种子配对、双榜筛选和报告没有 Steam 平台分支；平台差异位于启动器、原生宿主和引擎配置。
- 源码的 Steam/Epic 元数据各列出 78 个校验区间，地址集合相同，其中 10 个区间摘要不同。这只是两份已提交元数据的比较，未使用本机不存在的 Epic DLL 重新计算摘要，也不能证明内存对象布局和比赛行为相同。
- Epic 元数据包含非零启动状态标志，但没有 Epic 运行环境，无法验证真实授权初始化、依赖库装载及自然终场。
- `native_ai_tactics.h` 仍保留两个未映射的 AI 战术子读取入口。此路径由 `FM27_AI_TACTICS_SECTION` 控制，启动器清理外部传入的 `FM27_*` 环境变量；常规固定双方战术的属性实验不主动开启该路径。它不构成全部 AI 战术读取功能已支持的证据。
- Epic 元数据仍包含 `steam_api64.dll` 导入，宿主也保留相关环境设置和清理代码。不能只因名字包含 Steam 就删除这些依赖；是否需要额外 Epic 运行环境必须在正版 Epic 安装上验证。
- 打包使用官方 Epic 原生二进制，当前源码中的 native 改动没有重新编译进它。实际包通过完整目标 DLL 指纹把关；不要把源码的兼容策略说明视为这个二进制的逐项行为证明。
- 跨平台续跑受引擎 DLL、资源、宿主、比赛样本和输入指纹校验约束。Steam 实验不能换成 Epic 引擎继续，以免混合实验结果。

发布状态保持“Epic 测试包，原生比赛待实机验证”。获得匹配的完整 Epic 安装后，仍必须运行默认 `--platform epic` 的全部验收；不能关闭版本检查或伪造指纹来跳过验证。
