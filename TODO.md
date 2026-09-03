# MDHelper TODO

## IMPORTANT!

- 阅读并遵守 `AGENTS.md` 。
- 阅读并遵守 `docs/ARCHITECTURE.md` 的依赖：GUI/TUI/CLI -> App -> Analysis/Services -> Core。

## 紧急任务（重要性由高到低）

## 待实现功能（重要性由高到低）

## 已完成

- [x] [Refactor] 分离绘图领域模型、结果组装与渲染职责。
- [x] [Refactor] 分离分析执行用例与结果导出用例。
- [x] [Refactor] 分离 GROMACS 输入准备、命令执行与结果解析职责。
- [x] [Refactor] 分离 GUI 绘图页面的状态编排与控件渲染职责。
- [x] [Refactor] 移除名不副实的 plugins 包并归位分析流水线契约。
- [x] [Refactor] 细分核心分析与绘图契约。
- [x] [Refactor] 分离径向分析的帧处理、邻域搜索、曲线计算与壳层诊断。
- [x] [Refactor] 分离结构化数据导出与图片导出。
- [x] [Refactor] 分离外部进程记录、终端启动与进程生命周期。
- [x] [Refactor] 分离配置契约、解析与持久化。
- [x] [Refactor] 分离 TUI 分析导航、参数编辑与任务队列职责。
- [x] [Refactor] 分离 GUI 系统检查、文件监视、角色操作与帮助窗口职责。

## 完成标准（每轮代码改动后需重新确认）

- Ruff 和 mypy 通过。
- Windows/Linux 全部测试通过。
