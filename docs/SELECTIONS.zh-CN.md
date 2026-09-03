# 原子与组选择

[English](SELECTIONS.md) | [简体中文](SELECTIONS.zh-CN.md)

一次运行的选择语法由一个 Backend 负责。MDAnalysis 使用 NDX group 或静态 MDAnalysis
expression。GROMACS 使用 NDX group 或原生 `gmx rdf` expression。Result 记录 language 和
source。

Topology 和 trajectory 必须描述相同原子并保持相同顺序。原子数相同不能证明顺序匹配。
MDHelper 不根据文件名推断配对。

## NDX Group

通过 `--index` 传入 index 文件，再用精确 group name 指定 `--reference` 和 `--selection`：

```text
[ Cations ]
1 8 15

[ Solvent oxygen ]
2 5 9 12
```

NDX atom number 从一开始，MDHelper 将其转为零基索引。Group name 区分大小写且必须唯一。
支持分号注释和跨行 atom list。解析拒绝 header 前数据、非法或越界编号、重复 group 或 atom、
选中的空 group，以及没有 group 的文件。

进程内诊断记录 group、parser version、数量、有序索引 SHA-256、路径和文件 SHA-256。
GROMACS 自行解析 NDX；MDHelper 记录 group、路径和命令。

## Expression

没有 NDX 时，`mdanalysis` 使用 MDAnalysis 2.x selection language，`gromacs` 把 expression
传给 `gmx rdf -ref` 和 `-sel`。Auto 使用所选完整 Backend 的 parser。

| Selector | 含义 | 示例 |
| --- | --- | --- |
| `all` | 所有原子 | `all` |
| `name` | Atom name 或 pattern | `name O*` |
| `type` | Topology atom type | `type OW` |
| `element` | 元素 | `element O` |
| `resname` | Residue name | `resname SOL` |
| `resid` | Residue ID 或范围 | `resid 10:20` |
| `index` | 零基 atom index | `index 0 4 8` |
| `bynum` | 一基 atom number | `bynum 1:10` |

使用 `and`、`or`、`not` 和括号。Shell expression 需要引号。缺失 topology attribute 时失败。
不支持 `species`、`molecule` 等自定义 alias。

RDF 方法要求固定 atom identity。MDAnalysis 拒绝 `around`、`sphzone`、`sphlayer`、
`isolayer`、`cyzone`、`cylayer`、`point`、`prop` 和 `same x/y/z as`。动态选择需要独立的
method version。
