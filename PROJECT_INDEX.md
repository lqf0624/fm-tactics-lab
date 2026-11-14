# FM27 战术实验室 · 全局索引

## 新对话从这里开始

1. 根据用户描述，在下表找对应主题。先读 `PRD.md` 的相关段落与验收编号，再读该主题的任务记录。任务记录给出代码入口和已排除的原因。
2. 核对当前代码、用户正在使用的 EXE 版本和未提交改动。涉及实验时，先分清存档日期、主客场及实验编号；在副本上复现。
3. 完成后，在对应任务文件中**覆盖更新**「进度与证据」「试错与结论」「下次验证」。新主题在 `docs/tasks/` 下新建一份同结构的文件。记录版本、复现条件、实际结果和剩余问题；原始日志留在运行目录。
4. 产品行为或验收口径改变时，改写 PRD 的对应段落。文件职责或入口改变时才改本索引。日常进度只写入任务记录。

## 文件职责

| 要找什么 | 文件与职责 |
|---|---|
| 全局产品要求 | [PRD.md](PRD.md) — 目标、场景、页面职责、业务规则与验收基线 |
| 本地数据保护 | [LOCAL_BACKUP.md](docs/LOCAL_BACKUP.md) — 数据范围、快照、恢复和待验收项 |
| 中文姓名、球衣号码、球队切换 | [roster-identity.md](docs/tasks/roster-identity.md) — 两季存档的阵容读取、姓名顺序与号码证据 |
| 升降级、对手、阿森纳主教练 | [league-opponents.md](docs/tasks/league-opponents.md) — 联赛范围、主教练识别、主客场验证 |
| 针对性指令、历史结果、实验续跑 | [experiment-results.md](docs/tasks/experiment-results.md) — 指令作用对象、结果汉化和 Windows 文件占用复测 |
| 五大联赛选队与两轮测试 | [five-league-testing.md](docs/tasks/five-league-testing.md) — 96队目录、跨联赛对手、两轮种子与取消续跑验收 |
| 换电脑、词库与运行依赖 | [portability.md](docs/tasks/portability.md) — v1114.6 全新数据目录、迁移路径、中文覆盖、系统运行库及数据迁移边界 |
| 安装、操作及已知故障 | [README.md](README.md) 是用户手册；[TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) 是启动和引擎诊断；[SIMULATION_FIDELITY.md](docs/SIMULATION_FIDELITY.md) 说明模拟和统计口径 |
| 构建与交付 | [DEVELOPMENT.md](docs/DEVELOPMENT.md) 是上游构建说明；[RELEASE_CHECK.md](docs/RELEASE_CHECK.md) 是发布检查；[CONTRIBUTING.md](CONTRIBUTING.md) 说明私有数据边界；[tests/](tests/) 存放可复跑的回归用例 |
