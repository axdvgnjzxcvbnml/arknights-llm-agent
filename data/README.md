# data —— 数据目录

| 子目录 | 内容 | 是否进入仓库 |
|---|---|---|
| `prts_raw/` | PRTS Wiki 原始爬取数据（版权风险） | 否（.gitignore） |
| `vector_store/` | ChromaDB 向量库 | 否（.gitignore） |
| `graph/` | 知识图谱文件 | 否（.gitignore） |
| `sft_data/` | SFT 训练数据 | 否（.gitignore） |
| `mock/` | Mock 数据（假截图 / 假状态 / 假检索结果），冒烟测试用 | 是 |

gitignore 目录由对应脚本自动 `mkdir -p` 创建，clone 后无需手动准备。
