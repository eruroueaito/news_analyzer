#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
热点数据管理模块 - 管理 7 天内的新闻热点数据

每天保存热度最高的 100 条新闻，供趋势图分析使用。
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional


class HotNewsManager:
    """
    热点新闻数据管理器

    每天存储热度最高的 100 条新闻，支持最多 7 天的历史数据保留。
    提供关键词频率查询接口，用于趋势折线图。

    存储路径：{data_dir}/hot/YYYYMMDD.json
    """

    MAX_DAILY_ITEMS = 100

    def __init__(self, data_dir: str):
        self.logger = logging.getLogger('news_analyzer.processing.hot_news_manager')
        self.data_dir = Path(data_dir) / 'hot'
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _date_key(self, dt: Optional[datetime] = None) -> str:
        return (dt or datetime.now()).strftime('%Y%m%d')

    def _day_file(self, date_key: str) -> Path:
        return self.data_dir / f"{date_key}.json"

    def update_daily_hot(self, news_items: List[Dict], clusters: List[Dict] = None):
        """
        将当天热点新闻保存到文件（原子写入）

        Args:
            news_items: 新闻列表
            clusters: 聚类数据，用于提取 heat_score（可选）
        """
        if not news_items:
            return

        # 从聚类数据中建立 index → heat 映射
        heat_map: Dict[int, float] = {}
        if clusters:
            for cluster in clusters:
                for idx in cluster.get('news_indices', []):
                    heat_map[idx] = cluster.get('heat', 0)

        enriched = []
        for i, item in enumerate(news_items):
            enriched.append({
                'title': item.get('title', ''),
                'description': (item.get('description', '') or '')[:300],
                'source': item.get('source', item.get('source_name', '')),
                'category': item.get('category', ''),
                'pub_date': item.get('pub_date', ''),
                'heat_score': heat_map.get(i, 0),
                'keywords': item.get('keywords', []),
            })

        enriched.sort(key=lambda x: x['heat_score'], reverse=True)
        top_items = enriched[:self.MAX_DAILY_ITEMS]

        date_key = self._date_key()
        payload = {
            'date': date_key,
            'updated_at': datetime.now().isoformat(),
            'items': top_items,
        }

        try:
            tmp = self._day_file(date_key).with_suffix('.tmp')
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            tmp.replace(self._day_file(date_key))
            self.logger.info(f"已保存 {len(top_items)} 条热点新闻 ({date_key})")
        except Exception as e:
            self.logger.error(f"保存热点新闻失败: {e}")

    def get_hot_news(self, days: int = 7) -> List[Dict]:
        """
        获取最近 N 天的热点新闻，按 heat_score 降序排列

        Args:
            days: 天数

        Returns:
            合并后的新闻列表，每条附加 '_date' 字段
        """
        result = []
        now = datetime.now()
        for i in range(days):
            d = now - timedelta(days=i)
            path = self._day_file(self._date_key(d))
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding='utf-8'))
                    for item in data.get('items', []):
                        item['_date'] = data['date']
                        result.append(item)
                except Exception as e:
                    self.logger.warning(f"读取热点文件失败 {path}: {e}")

        result.sort(key=lambda x: x.get('heat_score', 0), reverse=True)
        return result

    def cleanup_old_data(self, max_days: int = 7):
        """删除超过 max_days 天的热点文件"""
        cutoff = datetime.now() - timedelta(days=max_days)
        cutoff_key = self._date_key(cutoff)
        removed = 0
        for p in self.data_dir.glob('*.json'):
            name = p.stem
            if name.isdigit() and name < cutoff_key:
                try:
                    p.unlink()
                    removed += 1
                except Exception as e:
                    self.logger.warning(f"删除旧热点文件失败 {p}: {e}")
        if removed:
            self.logger.info(f"已清理 {removed} 个旧热点文件")

    def get_keyword_frequency(self, keyword: str, days: int = 30) -> List[Dict]:
        """
        统计关键词在最近 N 天中每天的出现次数

        Args:
            keyword: 关键词（不区分大小写）
            days: 统计天数

        Returns:
            [{'date': 'YYYYMMDD', 'count': int}, ...] 按日期升序
        """
        kw = keyword.lower()
        results = []
        now = datetime.now()

        for i in range(days - 1, -1, -1):
            d = now - timedelta(days=i)
            date_key = self._date_key(d)
            path = self._day_file(date_key)
            count = 0

            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding='utf-8'))
                    for item in data.get('items', []):
                        text = (
                            (item.get('title', '') or '') + ' ' +
                            (item.get('description', '') or '')
                        ).lower()
                        if kw in text:
                            count += 1
                except Exception:
                    pass

            results.append({'date': date_key, 'count': count})

        return results
