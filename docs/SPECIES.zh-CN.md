# 物种识别与角色确认

[English](SPECIES.md) | [简体中文](SPECIES.zh-CN.md)

MDHelper 0.1.0 按 topology residue identity 识别 species，并统计不同的 topology-derived
`molecule_id`。识别只描述事实，不会根据 residue name 静默指定化学角色。

`mdhelper inspect` 返回带版本的系统摘要和每个 species 的可解释建议。atom charge 完整时，
始终为正的 molecule net charge 建议 `cation`，始终为负建议 `anion`，绝对容差为 `0.25 e`。
在始终中性的 species 中，唯一 population 最大者得到低置信度 `solvent` 建议。仅凭数量不能
区分 solvent、additive 或其他中性组分，因此会显示证据和歧义。charge 缺失、符号混合或
中性数量并列时返回 unavailable、候选角色和理由，不猜测。

每条建议包含 method、evidence、confidence、candidate roles、reason 和
`requires_user_confirmation = true`。CLI 用结构化的
`--roles '{LI: cation, SOL: solvent}'` 显式确认；GUI 显示同一建议，要求确认并允许编辑。
接受或覆盖的决定进入 request parameter provenance；所有
前端在 result provenance 中得到规范化 decision record。已确认角色存入 project manifest，
`mdhelper project set-roles` 可替换该映射，不改变机器配置。

角色只为项目 metadata、analysis provenance 和结果解释保留化学上下文。它绝不生成或替换
atom selection、选择 cutoff/grid/algorithm 或改变数值。`inspect` 会发布该 policy 和所有
允许角色的定义，使 CLI/TUI/GUI 共享契约。

GUI 在完整 review dialog 中显示建议证据，不使用短暂 tooltip 或小字提示。批量应用仍会
询问确认，只填写 available suggestion；不可用或歧义 species 保持未设置，直到用户显式
选择。TUI 在确认前显示相同 method 和 reason。
