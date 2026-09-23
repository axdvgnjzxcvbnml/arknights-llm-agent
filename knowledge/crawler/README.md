# crawler —— PRTS Wiki 爬虫

- `prts_crawler.py`：爬虫入口，支持干员 / 敌人 / 关卡 / 攻略四类页面
- `parse_operators.py`：解析干员数据
- `parse_enemies.py`：解析敌人数据
- `parse_stages.py`：解析关卡数据
- `parse_guides.py`：解析攻略文本

输出 JSON 到 `data/prts_raw/`（已 gitignore，**不进入公开仓库**，版权风险）。
带限速与重试，避免对 PRTS Wiki 造成压力。第二批实现。
