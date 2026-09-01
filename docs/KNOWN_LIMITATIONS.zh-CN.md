# MDHelper 0.1.0 已知限制

[English](KNOWN_LIMITATIONS.md) | [简体中文](KNOWN_LIMITATIONS.zh-CN.md)

- RDF method 1.0.0 面向三维周期 bulk 体系中的静态原子选择；不支持质心、slab、取向、
  动态选择、仅分子间或 site-exclusion RDF 变体。
- RDF 和累积 RDF 基础结果是所选帧上的确定值。0.1.0 不估计平衡、相关时间、
  statistical inefficiency、收敛性、不确定度或有效样本量。
- 第一最小值检测是可解释诊断，可能不可用或置信度低。累积 RDF 可报告该边界的运行值供
  复核，但不会改变曲线。
- 物种角色仅为建议，不提供化学感知。只有 topology charge 完整时才使用净电荷符号；中性
  population 优势只有低置信度，所有角色都需要确认。
- 输入原子身份固定；依赖坐标的 MDAnalysis 选择会被拒绝。
- MDHelper GRO Reader 只支持单帧或多帧 GRO。XTC/TRR 和 TPR 支持取决于内置 MDAnalysis；较新
  TPR 可能需要兼容的 GRO/PDB topology snapshot。TNG 是 GROMACS 轨迹格式，但当前
  MDAnalysis/PyTNG reader 不能可靠读取有效的 GROMACS TNG 输出，因此 MDHelper 0.1.0
  不支持 TNG。
- GROMACS 是可选工具。Auto 可在前序完整候选无法加载输入后选择已检测的完整 GROMACS
  流水线；显式 `gromacs` RDF/CN 使用已安装的 `gmx trjconv` 和 `gmx rdf`，数值行为可能随
  GROMACS 版本变化。能力检测后仍由用户负责外部程序兼容性。
- Windows 和 Linux 便携归档 smoke test 必须在各自发布工作流中实际通过；工作流文件存在
  不能证明发布成功。
- 当前有界电解液回归数据和手算通用体系覆盖已发布分析；仍希望增加第二份独立来源的生产
  MD 轨迹作为补充证据。

每个 observable 的容差见版本匹配的 [methods](methods/README.zh-CN.md) 和
[validation](validation/) 文档。
