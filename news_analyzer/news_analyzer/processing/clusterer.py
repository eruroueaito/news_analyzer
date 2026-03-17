"""
新闻聚类模块

使用 KMeans 算法对 TF-IDF 向量化后的新闻进行聚类分析，
自动发现新闻热点话题，并计算每个话题的热度值。

功能：
    - 自动确定最优聚类数量
    - KMeans 聚类分析
    - 聚类关键词提取
    - 热度评分计算（综合文章数量、来源多样性、时效性）
    - 聚类结果可视化配色
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from math import sqrt
from typing import Any

import numpy as np
from scipy.sparse import spmatrix
from sklearn.cluster import KMeans

logger = logging.getLogger(__name__)

# ============================================================
# 聚类可视化配色方案
# 选取 15 种在深色和浅色背景上都有良好可读性的颜色
# ============================================================
CLUSTER_COLOR_PALETTE: list[str] = [
    "#E63946",  # 红色 - 鲜明醒目
    "#2A9D8F",  # 青绿色 - 沉稳专业
    "#E9C46A",  # 金黄色 - 温暖活力
    "#264653",  # 深蓝灰 - 严肃稳重
    "#F4A261",  # 橘色 - 热情友好
    "#6A4C93",  # 紫色 - 典雅高贵
    "#1982C4",  # 蓝色 - 科技现代
    "#8AC926",  # 黄绿色 - 清新自然
    "#FF595E",  # 珊瑚红 - 活泼醒目
    "#6A994E",  # 草绿色 - 自然和谐
    "#BC4749",  # 砖红色 - 庄重传统
    "#48BFE3",  # 天蓝色 - 轻盈明快
    "#F77F00",  # 深橙色 - 热烈积极
    "#7209B7",  # 深紫色 - 神秘高贵
    "#3A86A7",  # 钢蓝色 - 冷静专业
]


def _dedup_prefix_keywords(keywords: list[str]) -> list[str]:
    """
    移除关键词列表中的近似重复词。

    若词 B 以词 A 开头（且 A 长度 >= 4），则认为 B 是 A 的派生形式，
    保留 A（较短/更通用），丢弃 B。例如：
        ["america", "american"] → ["america"]
        ["iran", "iranian"]     → ["iran"]
    """
    result: list[str] = []
    for kw in keywords:
        dominated = any(
            len(existing) >= 4 and kw.startswith(existing) and kw != existing
            for existing in result
        )
        if not dominated:
            result.append(kw)
    return result


class NewsClusterer:
    """
    新闻聚类分析器

    基于 KMeans 算法对新闻进行聚类，自动发现热点话题，
    并为每个话题计算热度评分。

    使用示例：
        clusterer = NewsClusterer()
        clusters = clusterer.cluster(tfidf_matrix, news_items, feature_names)
        for c in clusters:
            print(f"话题: {c['keyword']}  热度: {c['heat']}")
    """

    def __init__(self, n_clusters: int | None = None) -> None:
        """
        初始化聚类器

        Args:
            n_clusters: 聚类数量。如果为 None，则根据新闻数量自动计算。
                        自动计算公式: min(max(5, int(sqrt(n_items / 3))), 25)
        """
        self._n_clusters = n_clusters
        logger.info(
            "NewsClusterer 初始化完成（n_clusters=%s）",
            n_clusters if n_clusters else "自动检测",
        )

    def cluster(
        self,
        tfidf_matrix: spmatrix,
        news_items: list[dict],
        feature_names: list[str],
    ) -> list[dict]:
        """
        对新闻进行聚类分析

        Args:
            tfidf_matrix: TF-IDF 稀疏矩阵（行=文档，列=特征词）
            news_items: 原始新闻字典列表
            feature_names: 特征词名称列表，与 tfidf_matrix 的列一一对应

        Returns:
            聚类结果列表，按热度降序排列。每个聚类包含：
                - cluster_id: 聚类编号
                - keyword: 主关键词
                - related_keywords: 关联关键词列表
                - heat: 热度评分
                - news_indices: 属于该聚类的新闻索引列表
                - color: 可视化颜色（十六进制）
        """
        # 输入校验
        if tfidf_matrix is None or not news_items or not feature_names:
            logger.warning("聚类输入数据无效，返回空结果")
            return []

        n_items = tfidf_matrix.shape[0]

        # 确定聚类数量
        if self._n_clusters is not None:
            n_clusters = self._n_clusters
        else:
            n_clusters = self._auto_detect_clusters(n_items)

        # 确保聚类数不超过样本数
        n_clusters = min(n_clusters, n_items)

        if n_clusters < 1:
            logger.warning("聚类数量不足（n_clusters=%d），返回空结果", n_clusters)
            return []

        logger.info("开始 KMeans 聚类：样本数=%d, 聚类数=%d", n_items, n_clusters)

        # 执行 KMeans 聚类
        kmeans = KMeans(
            n_clusters=n_clusters,
            init="k-means++",       # 使用 k-means++ 初始化，加速收敛
            max_iter=300,           # 最大迭代次数
            n_init=10,              # 多次初始化取最优结果
            random_state=42,        # 固定随机种子，保证结果可复现
        )
        labels = kmeans.fit_predict(tfidf_matrix)
        cluster_centers = kmeans.cluster_centers_

        logger.info("KMeans 聚类完成，开始构建聚类结果...")

        # 构建聚类结果
        clusters: list[dict] = []
        for cluster_id in range(n_clusters):
            # 获取属于当前聚类的新闻索引
            news_indices = [
                int(idx) for idx, label in enumerate(labels) if label == cluster_id
            ]

            # 跳过空聚类
            if not news_indices:
                continue

            # 提取聚类中心的关键词
            center = cluster_centers[cluster_id]
            keyword, related_keywords = self._extract_cluster_keywords(
                center, feature_names
            )

            # 获取聚类内的新闻列表
            cluster_news = [news_items[i] for i in news_indices]

            # 计算热度评分
            heat = self._calculate_heat(cluster_news)

            # 分配颜色（循环使用调色板）
            color = CLUSTER_COLOR_PALETTE[cluster_id % len(CLUSTER_COLOR_PALETTE)]

            clusters.append(
                {
                    "cluster_id": cluster_id,
                    "keyword": keyword,
                    "related_keywords": related_keywords,
                    "heat": round(heat, 2),
                    "news_indices": news_indices,
                    "color": color,
                }
            )

        # 按热度降序排列
        clusters.sort(key=lambda c: c["heat"], reverse=True)

        # 重新分配排序后的 cluster_id（按热度排名）
        for rank, cluster in enumerate(clusters):
            cluster["cluster_id"] = rank

        logger.info("聚类分析完成：共生成 %d 个话题聚类", len(clusters))
        return clusters

    @staticmethod
    def _auto_detect_clusters(n_items: int) -> int:
        """
        根据新闻数量自动计算最优聚类数

        公式：min(max(5, int(sqrt(n_items / 3))), 25)
        - 最少 5 个聚类，确保话题分类的粒度
        - 最多 25 个聚类，避免过度碎片化
        - 使用平方根函数保证聚类数随样本量缓慢增长

        Args:
            n_items: 新闻样本数量

        Returns:
            推荐的聚类数量
        """
        n_clusters = min(max(5, int(sqrt(n_items / 3))), 25)
        logger.debug("自动检测聚类数：样本数=%d -> 聚类数=%d", n_items, n_clusters)
        return n_clusters

    @staticmethod
    def _extract_cluster_keywords(
        center: np.ndarray,
        feature_names: list[str],
        n_related: int = 5,
    ) -> tuple[str, list[str]]:
        """
        从聚类中心向量中提取主关键词和关联关键词

        聚类中心的每个维度值代表该特征词对聚类的重要程度，
        取值最高的词作为主关键词，次高的若干词作为关联关键词。

        Args:
            center: 聚类中心向量（一维数组）
            feature_names: 特征词名称列表
            n_related: 关联关键词数量（默认取前 3~5 个）

        Returns:
            (主关键词, 关联关键词列表) 的元组
        """
        # 按中心向量值降序排列
        sorted_indices = center.argsort()[::-1]

        # 主关键词：中心向量值最高的词
        primary_keyword = feature_names[sorted_indices[0]]

        # 关联关键词：中心向量值次高的若干词
        related_keywords = [
            feature_names[sorted_indices[i]]
            for i in range(1, min(n_related + 1, len(sorted_indices)))
            if center[sorted_indices[i]] > 0  # 仅保留有实际贡献的关键词
        ]

        # 去除近似重复词（如 america / american，iran / iranian）
        # 若某词是另一词的前缀（前缀长度 ≥ 4），则保留较短的那个
        all_kws = [primary_keyword] + related_keywords
        all_kws = _dedup_prefix_keywords(all_kws)
        primary_keyword = all_kws[0] if all_kws else primary_keyword
        related_keywords = all_kws[1:]

        return primary_keyword, related_keywords

    def _calculate_heat(self, news_items_in_cluster: list[dict]) -> float:
        """
        计算聚类的热度评分

        热度公式：文章数量 * 来源多样性系数 * 时效性权重

        - 文章数量：聚类内的新闻条数，直接反映话题的关注度
        - 来源多样性：不同新闻来源的数量，多来源报道说明话题更重要
        - 时效性权重：越近期的新闻权重越高，反映话题的时效性

        Args:
            news_items_in_cluster: 聚类内的新闻列表

        Returns:
            热度评分（浮点数）
        """
        if not news_items_in_cluster:
            return 0.0

        # 文章数量
        article_count = len(news_items_in_cluster)

        # 来源多样性系数：统计不同新闻源的数量
        sources = set()
        for item in news_items_in_cluster:
            source = item.get("source_name") or item.get("source", {}).get("name", "")
            if source:
                sources.add(source)
        # 至少算 1 个来源，避免乘以 0
        source_diversity_factor = max(len(sources), 1)

        # 时效性权重
        recency_weight = self._recency_weight(news_items_in_cluster)

        heat = article_count * source_diversity_factor * recency_weight
        return heat

    @staticmethod
    def _recency_weight(news_items: list[dict]) -> float:
        """
        计算新闻的时效性权重

        基于新闻发布时间与当前时间的差距，使用指数衰减函数计算权重：
        - 24 小时内的新闻：权重接近 1.0
        - 3 天前的新闻：权重约 0.5
        - 7 天前的新闻：权重约 0.2
        - 更早的新闻：权重逐渐趋近于 0.1（最低值）

        如果无法解析发布时间，返回默认权重 0.5。

        Args:
            news_items: 新闻列表

        Returns:
            时效性权重（0.1 ~ 1.0）
        """
        if not news_items:
            return 0.5

        now = datetime.now(timezone.utc)
        weights: list[float] = []

        for item in news_items:
            pub_date_str = item.get("pub_date") or item.get("publishedAt", "")
            if not pub_date_str:
                weights.append(0.5)  # 无日期时使用默认权重
                continue

            try:
                if isinstance(pub_date_str, datetime):
                    pub_date = pub_date_str
                elif isinstance(pub_date_str, str):
                    # 优先尝试 ISO 8601（Atom 格式：2026-03-17T12:00:00Z）
                    try:
                        pub_date = datetime.fromisoformat(
                            pub_date_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        # 回退到 RFC 2822（RSS 格式：Mon, 17 Mar 2026 12:00:00 GMT）
                        pub_date = parsedate_to_datetime(pub_date_str)
                else:
                    weights.append(0.5)
                    continue

                # 确保时区一致
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)

                # 计算时间差（小时）
                hours_ago = (now - pub_date).total_seconds() / 3600.0
                hours_ago = max(hours_ago, 0)  # 防止未来时间产生负值

                # 指数衰减函数：半衰期约 72 小时（3天）
                # weight = 0.1 + 0.9 * exp(-hours_ago / 72)
                weight = 0.1 + 0.9 * (2.0 ** (-hours_ago / 72.0))
                weights.append(min(weight, 1.0))

            except (ValueError, TypeError, OverflowError) as e:
                logger.debug("无法解析新闻发布时间 '%s'：%s", pub_date_str, e)
                weights.append(0.5)

        # 返回所有新闻权重的平均值
        return sum(weights) / len(weights) if weights else 0.5
