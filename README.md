# Retron · 有机合成工作台

> 一个**完全离线运行**的有机合成桌面工具 —— 在自己的电脑上画结构式、做结构/名称互转、倒推合成路线、补全反应条件、预测反应产物。
>
> **断网可用 · 数据不出本机 · 永久免费**

---

## 为什么做这个

做有机合成时经常要开一堆在线工具：画结构的、查名字的、算分子式的、设计路线的 —— 大多数要么收费订阅，要么要求把结构上传到别人的服务器。

Retron 把这些事情全都搬到本机：装上就能用，拔掉网线照样跑，画的结构、查的分子、设计的路线**一个字节都不会离开你的电脑**。

---

## 功能一览

| 功能 | 你能做什么 |
|---|---|
| **画板** | 中文界面的结构式/反应式编辑器，支持从图片粘贴识别、从其他化学软件粘贴结构 |
| **结构 ⇄ 名称互转** | 输入 `阿司匹林` / `aspirin` / `CC(=O)Oc1ccccc1C(=O)O` 中任意一种，输出另外几种（含分子式、InChI）<br>词典覆盖 **近 20 万化合物、320 多万条别名俗名** |
| **逆合成路线设计** | 给一个目标分子，自动倒推多条合成路线（正向合成顺序排列，每步标注原料是否可购买）<br>支持指定起始原料：从「我手里有的原料 A」出发设计到目标 B 的路线 |
| **反应条件补全** | 给路线每一步补上**试剂、溶剂、催化剂、温度**建议（68 万条文献先例 + 命名反应规则） |
| **正向反应预测** | 给反应物，预测最可能生成的产物（ReactionT5v2，USPTO 数据微调） |
| **图片识别结构** | 把论文/软件里的结构式截图直接粘进来，自动识别成可编辑的分子（MolScribe 主力 + DECIMER 兜底） |
| **一键上画板** | 逆合成结果可以逐步或整条画到画板上对照，反应条件同步显示，已画内容不会被覆盖 |

---

## 快速开始

### 方式一：用打包好的完整版（推荐）

1. 从 [Releases](../../releases) 下载完整版压缩包
2. 解压到任意目录（路径含中文也没问题）
3. 双击 `Retron/Retron.exe`

首次启动会自动完成环境适配与桌面快捷方式创建。**不需要安装 Python，不需要联网。**

### 方式二：从源码搭建

前置：Windows 10/11 x64、Python 3.11（[python.org](https://www.python.org/downloads/)）

```bash
git clone <this-repo>
cd Retron-Source

# 1) 建基准解释器与五套环境
#    把 Python 3.11 放到 tools/python311/
tools/python311/python.exe -m venv tools/venv
tools/python311/python.exe -m venv tools/venv-retro
#    ... 其余三套同理（venv-vision / venv-forward / venv-conditions）

# 2) 按清单装依赖
tools/venv/Scripts/pip.exe install -r tools/requirements/requirements-base.txt
#    ... 其余四套同理

# 3) 准备模型与数据（见下方「模型与数据来源」）

# 4) 启动外壳
cd shell && npm install && npm start
```

> 各环境的依赖清单在 `tools/requirements/` 下，按环境分别导出，可直接复现。

---

## 技术架构

程序分成**一个外壳 + 一个本地服务 + 五个独立引擎**：

```
桌面外壳（Electron）
   └─ 静默拉起本地服务（127.0.0.1:8765，无命令行窗口）
         ├─ 转换引擎   RDKit + 自建词典 + OPSIN      → tools/venv
         ├─ 逆合成引擎 AiZynthFinder (MCTS)          → tools/venv-retro
         ├─ 识图引擎   MolScribe / DECIMER           → tools/venv-vision
         ├─ 正向预测   ReactionT5v2                  → tools/venv-forward
         └─ 条件推荐   DRFP 指纹 + 先例检索          → tools/venv-conditions
```

**为什么分五个环境**：这几个引擎的依赖互相冲突（不同版本的 PyTorch、TensorFlow、OpenNMT），混在一起装不通。分开后各自独立、互不干扰，某个引擎坏了也不影响其他功能。

**为什么用本地 HTTP 服务**：界面（网页技术）和引擎（Python）通过本机回环地址通信，不经过网络。这样界面能做得漂亮，引擎能自由用 Python 生态，两边松耦合。

---

## 目录结构

```
Retron-Source/
├── app/
│   └── server.py              本地服务：接口路由 + 引擎进程管理
├── engine/                    五个引擎（各自独立）
│   ├── chemistry/             结构/名称/分子式互转
│   ├── retro/                 逆合成路线设计
│   ├── vision/                图片识别结构
│   ├── forward/               正向反应预测
│   └── conditions/            反应条件推荐
├── web/                       界面
│   ├── index.html             主界面（三标签页）
│   ├── board.html             画板页
│   └── ketcher/               化学画板（Ketcher，已汉化）
├── shell/                     Electron 桌面外壳
│   ├── main.js                启动/退出/环境自愈
│   └── package.json
├── tools/
│   ├── repair_env.py          换电脑后自动修环境路径
│   ├── check_runtime_deps.py  运行环境依赖体检
│   ├── requirements/          五套环境的依赖清单
│   └── archived-scripts/      开发期测试脚本（CDP 端到端验证等）
├── 使用说明.md                给使用者的说明
└── 蓝图.md                    技术设计文档
```

运行期还需要（**不在仓库里**，体积原因）：

```
data/       模型与数据（约 4.8 GB）
tools/      五套 Python 环境 + 基准解释器（约 8 GB）
```

---

## 用到的开源项目

| 组件 | 用途 | 许可证 |
|---|---|---|
| [Ketcher](https://github.com/epam/ketcher) | 化学画板 | Apache-2.0 |
| [RDKit](https://www.rdkit.org/) | 化学结构计算 | BSD-3-Clause |
| [AiZynthFinder](https://github.com/MolecularAI/aizynthfinder) | 逆合成搜索 | MIT |
| [OPSIN](https://github.com/dan2097/opsin) | 英文系统名 → 结构 | MIT |
| [MolScribe](https://github.com/thomas0809/MolScribe) | 结构式图片识别 | MIT |
| [DECIMER](https://github.com/Kohulan/DECIMER-Image_Transformer) | 结构式图片识别（兜底） | MIT |
| [ReactionT5v2](https://huggingface.co/sagawa/ReactionT5v2-forward-USPTO_MIT) | 正向反应预测 | MIT |
| [Electron](https://www.electronjs.org/) | 桌面外壳 | MIT |

---

## 模型与数据来源

所有模型与数据均自公开来源下载后**落盘本地**，运行期零联网：

| 数据 | 来源 | 本地位置 |
|---|---|---|
| 可购买化合物库（1742 万条） | AiZynthFinder 提供的 Zinc 库 | `data/retro/zinc_stock.hdf5` |
| 逆合成模型（USPTO 训练） | AiZynthFinder 官方权重 | `data/retro/*.onnx` |
| 正向预测模型 | `sagawa/ReactionT5v2-forward-USPTO_MIT` (HuggingFace) | `data/forward/模型/` |
| 结构识别模型 | MolScribe / DECIMER 官方权重 | `data/vision/models`、`data/vision/pystow` |
| 反应条件先例（68 万条） | USPTO_Condition 数据集 | `data/conditions/` |
| 化合物词典（20 万化合物 / 320 万别名） | PubChem / Wikidata / 药品目录 | `data/中文名字典.sqlite` |

---

## 已知限制

- **仅支持 Windows x64**。核心是 Python 引擎（跨平台），但外壳与路径自愈逻辑按 Windows 编写。
- **逆合成首次启动较慢**（要加载 "可购买化合物库" 与模型，约 1 分钟），之后每次约 20 秒。
- **图片识别对印刷体准确率高**，手绘草稿和复杂立体构型会有偏差，识别后建议人工核对。
- **与其他化学软件之间**：支持"复制结构 → 本页面粘贴"（带文本直接用，纯图片走识别）；各家私有格式不公开，无法做到 Ctrl+C/Ctrl+V 一键无损直通。
- 路线与产物预测是**基于文献数据的建议**，实际可行性请以实验为准。

---

## 许可证

本项目代码采用 [MIT 许可证](LICENSE)。

`web/ketcher/` 下为 Ketcher 的构建产物，遵循其 Apache-2.0 许可证；各引擎调用的第三方开源组件版权归各自作者所有（见上表）。

---

## 致谢

没有这些开源项目，这个工具不可能存在：AiZynthFinder（阿斯利康）、RDKit、Ketcher（EPAM）、OPSIN、MolScribe、DECIMER、ReactionT5v2、Electron。
