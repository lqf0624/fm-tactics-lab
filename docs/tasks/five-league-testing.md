# 五大联赛选队与两轮实验

对应 PRD A9、A10。进度：**v1114.6 已完成验收**。

## 进度与证据
- 当前2028-04-08存档：英超20、西甲20、法甲18、德甲18、意甲20，共96队；全部名单读取通过，共2812名有效唯一ID的一线队球员。
- 五队（阿森纳、Athletic Club、Auxerre、Bayer Leverkusen、Milan）每队两轮20场，共100场。第一轮8条、第二轮12条，第二轮A/B各6场，配对数6。
- 阿森纳对米兰跨联赛20场，首轮完成后于第二轮取消，再续跑至20场，无重复。手选首发保留23人名单。
- 120场原生自然终场、输入二进制及逐场日志哈希独立复核通过；双方针对性及指定盯人关闭。
- 页面实测五队55名首发姓名与当季号码；其中54名有中文译名，Athletic Club 的 Nico Williams 保留原名。结果页与CSV分轮字段一致。168项代码回归：164通过、4环境用例跳过。独立代码审查和复核通过。中文覆盖更正及异机重读证据见 [portability.md](portability.md)。
- 补测浏览器慢对手请求后换队，旧响应被丢弃（switch-race-acceptance.json）；三档2027-02-06/2028-04-01/2028-04-08南安普顿归属核对通过。
- 最终解包源文件与工作区 Python/JS/CSS/HTML 全部一致。构建入口 build/package_five.py，解包验收目录 build/five-smoke；EXE SHA256 见验收文档。
- 本地交付包 FM27-Tactics-Lab-1114.6.exe 的[验收与用法](../V1114_6_VALIDATION.md)。PR 仅提交源码，EXE 不随 Git 提交。详细证据在 build/five-qa：acceptance.json、extra-acceptance.json、all-rosters.json、verification.json、ui-acceptance.json、results-ui-acceptance.json。

## 设计与代码入口
- [desktop_league_testing.py](../../src/desktop_league_testing.py)：稳定赛事数据库ID匹配五大联赛；当季成员、非执教队名单、跨联赛对手和保存战术来源。
- [desktop_test_rounds.py](../../src/desktop_test_rounds.py)：两轮不重叠种子、排名与针对性禁用。
- [desktop_save_mode.py](../../src/desktop_save_mode.py)、[desktop_opponent_scope.py](../../src/desktop_opponent_scope.py)：存档入口、按需读取、完整赛程目录回退。
- [fm27_tactics_server.py](../../src/fm27_tactics_server.py)：两轮顺序执行、分轮统计、持久化与续跑校验。
- [league-testing.js](../../src/tactics_ui/league-testing.js)、[save-mode.js](../../src/tactics_ui/save-mode.js)：联赛/球队筛选、异步切换隔离、两轮控制及结果；desktop.js 导出轮次。
- [test_five_league_testing.py](../../tests/test_five_league_testing.py)：赛季与缺联赛、国外赛程、替补保留、种子边界和原生标记回归。

## 试错与结论
- 原入口限制人类执教球队；其他队通常没有保存战术。采用现有存档模式扩展，可明确“沿用当前战术板”读取真实名单。未另建重复界面，未把预设说成当天实战。
- 针对性禁用最初整行重建丢掉 personal 原生格式标志，准备阶段报错。现在只清四项设置，保留格式，回归及实赛通过。
- dataset.fixtures 的压缩列表不足以覆盖国外球队；使用经读取器完整赛程验证的 leagues 目录作回退，仍按日期区分赛季。
- 审查发现并修正：手选首发丢替补、第二轮卡片混入首轮配对统计、换队后旧异步请求覆盖新清单、单方案/并列错误标领先。
- 全量验证时发现无唯一ID的占位记录；与软件读取规则一致地排除，所有96队仍有足够不同一线队球员。
- 用户确认两轮口径；采用现有A/B对照，第一轮筛选，第二轮保留对照复测。仅一个方案时为重复验证，不宣称优胜。对手上限120覆盖全部五大联赛选择。

## 数据保护与下次验证
原始 .fm 只读；验收用 build/five-qa 独立副本，生产存档缓存与原战术优化数据未被覆盖。新版沿用用户本地数据目录。个人战术优化实验不包含在本次源码贡献中。
换档/跨季继续跑 A3、A9、A10；旧请求不得覆盖新选择；未加载联赛和不足11名可读球员须明确报错。完整本地备份/恢复仍按 LOCAL_BACKUP.md 后续开发，不声称本版实现。
