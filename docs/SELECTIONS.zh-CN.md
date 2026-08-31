# 原子与组选择

[English](SELECTIONS.md) | [简体中文](SELECTIONS.zh-CN.md)

MDHelper 0.1.0 通常在流式读取轨迹前，把选择解析为固定、有序、零基原子索引 tuple。首选
来源是 GROMACS `.ndx` 组；没有 NDX 时，内置分析使用静态 MDAnalysis expression。显式
GROMACS RDF/CN 则把 request expression 作为 GROMACS selection syntax 传给 `gmx rdf`。
所有路径都在统一结果契约中记录 selection language 和 source。

## 首选：GROMACS index group

使用 `gmx make_ndx` 等工具创建的文件可通过 `--index` 传入。分析的 `reference` 和
`selection` 参数是精确组名，包括空格：

```text
[ Cations ]
1 8 15

[ Solvent oxygen ]
2 5 9 12
```

```bash
mdhelper rdf \
  --topology topol.tpr --trajectory md.xtc --index index.ndx \
  --reference "Cations" --selection "Solvent oxygen" \
  --r-max 1.0 --bin-width 0.002 --output results/rdf
```

NDX 使用一基编号，MDHelper 转为内部零基索引。组名大小写敏感且必须唯一；支持分号注释和
跨行 atom list。以下情况直接失败：header 前数据、非整数/越界编号、重复组名、组内重复
原子、选中的空组以及没有任何组。程序不会静默去重或 clamp。

`index_file` 记录实际文件。它非 null 时，`reference` 和 `selection` 都是组名。诊断记录
group、parser version、解析数量、有序索引 SHA-256、规范
路径和文件 SHA-256。index 也是项目和 provenance 的指纹输入。

选择 topology、trajectory 和可选 index 文件后，GUI 会自动加载解析出的组。RDF 和
Cumulative Coordination Number 使用组选择器。切换到 expression source 会恢复自由表达式编辑器。

## 按 Backend 选择 expression syntax

没有 NDX 时进入 expression 模式。`native`、`mdanalysis` 和 `auto` 轨迹分析使用下述
MDAnalysis Atom Selection Language；显式 `gromacs` RDF/CN 把两个 expression 直接传给
GROMACS，应使用已安装版本的 `gmx rdf -ref` 和 `-sel` 语法。

常用稳定 topology selector：

| Selector | 含义 | 示例 |
| --- | --- | --- |
| `all` | 所有原子 | `all` |
| `name` | atom name，可用 shell pattern | `name O*` |
| `type` | topology atom type | `type OW` |
| `element` | 化学元素 | `element O` |
| `resname` | residue/species name | `resname SOL` |
| `resid` | topology residue ID，可用范围 | `resid 10:20` |
| `index` | 零基 atom index | `index 0 4 8` |
| `bynum` | 一基 atom serial | `bynum 1:10` |

Boolean operator 为 `and`、`or`、`not`，括号显式指定优先级。shell 中应给表达式加引号。
匹配遵循 MDAnalysis 2.x parser 和 topology 实际属性；缺失属性直接报错，不虚构 charge、
mass、molecule number 或 bond。旧自定义 alias `species`、`molecule` 不受支持。

## 固定身份限制

内置 RDF 和累积 RDF 要求固定 atom identity，因此拒绝：

```text
around, sphzone, sphlayer, isolayer, cyzone, cylayer, point, prop
same x as, same y as, same z as
```

在 dummy 或第一帧计算这些表达式会错误冻结动态选择。真正动态选择需要独立、带版本的逐帧
method，不属于 0.1.0 契约。
