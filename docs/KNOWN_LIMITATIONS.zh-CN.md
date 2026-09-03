# MDHelper 0.1.0 已知限制

[English](KNOWN_LIMITATIONS.md) | [简体中文](KNOWN_LIMITATIONS.zh-CN.md)

- RDF 支持三维周期 bulk 体系中的静态原子选择，不支持质心、slab、取向、动态、仅分子间或
  site-exclusion 变体。
- RDF 方法不估计平衡、自相关、收敛、不确定度或有效样本量。
- 第一壳层检测可能不可用，且不修改曲线。
- 物种角色建议需要 project 中存在无歧义的 `.itp` molecule 定义；解析器不处理依赖
  preprocessor 的 `[ moleculetype ]` 或 `[ atoms ]` section。
- 进程内格式支持取决于内置 MDAnalysis。0.1.0 不支持 TNG。
- GROMACS 是可选依赖。能力检测后，其版本仍可能影响外部 Backend 结果。
- 发布工作流定义不能证明目标平台 smoke test 已通过。
- 当前验证缺少第二份独立来源的生产轨迹。

方法范围和检查见[方法](methods/README.zh-CN.md)与[验证](validation/)。
