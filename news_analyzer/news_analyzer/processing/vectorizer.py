"""
新闻文本向量化模块

使用 TF-IDF 算法结合 jieba 中文分词，将新闻文本转换为数值向量表示。
主要用于后续的新闻聚类和关键词提取。

功能：
    - 中文文本分词（基于 jieba）
    - TF-IDF 特征提取
    - 关键词排序与提取
    - 中文停用词过滤
"""

from __future__ import annotations

import logging
from typing import Any

import jieba
from scipy.sparse import spmatrix
from sklearn.feature_extraction.text import TfidfVectorizer

logger = logging.getLogger(__name__)

# ============================================================
# 中文停用词表
# 包含常见的中文虚词、助词、连词、介词等，用于过滤无意义的高频词
# ============================================================
CHINESE_STOP_WORDS: set[str] = {
    # 代词
    "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们",
    "自己", "什么", "哪", "哪些", "谁", "怎么", "怎样", "多少",
    "这", "那", "这些", "那些", "这个", "那个", "这里", "那里",
    # 助词、语气词
    "的", "了", "着", "过", "吗", "吧", "呢", "啊", "呀", "哦",
    "嗯", "哈", "么", "嘛", "啦", "噢", "喔", "罢了", "而已",
    # 介词
    "在", "从", "到", "向", "对", "以", "把", "被", "给", "跟",
    "和", "与", "及", "或", "同", "比", "让", "将", "由",
    # 连词
    "因为", "所以", "但是", "但", "而", "而且", "并且", "不过",
    "然而", "如果", "虽然", "虽", "即使", "无论", "不管", "只要",
    "只有", "除非", "否则", "于是", "因此", "所", "既", "又",
    # 副词
    "不", "没", "没有", "很", "非常", "十分", "太", "最", "更",
    "也", "都", "就", "才", "只", "已", "已经", "曾", "曾经",
    "正在", "将要", "可能", "一定", "必须", "应该", "可以", "能",
    "能够", "还", "再", "又", "刚", "刚才", "总是", "常常", "经常",
    "往往", "大约", "差不多", "几乎", "简直", "究竟", "到底",
    # 动词（高频无意义）
    "是", "有", "说", "做", "去", "来", "看", "想", "要", "会",
    "能", "得", "让", "使", "叫", "知道", "觉得", "认为", "成为",
    # 量词、数词
    "个", "一", "二", "三", "两", "些", "每", "各", "第",
    # 方位词
    "上", "下", "中", "前", "后", "里", "外", "内", "左", "右",
    # 其他高频虚词
    "人", "大", "为", "国", "们", "好", "时", "年", "月", "日",
    "时候", "地方", "东西", "事情", "问题", "方面", "情况", "关系",
    "之", "其", "此", "某", "该", "本", "各种", "任何", "一些",
    "一切", "所有", "其他", "另", "别", "等", "等等", "如此",
    "这样", "那样", "怎样", "如何", "为什么", "什么样",
    # 标点符号及特殊字符（分词后可能残留）
    ".", ",", "!", "?", ";", ":", "'", '"', "(", ")",
    "。", "，", "！", "？", "；", "：", "'", "'", """, """,
    "（", "）", "【", "】", "《", "》", "、", "…", "——",
    "\n", "\t", " ", "\r",
}


class NewsVectorizer:
    """
    新闻文本向量化器

    将新闻标题和描述文本通过 TF-IDF 算法转换为稀疏矩阵，
    同时支持关键词提取功能。

    使用示例：
        vectorizer = NewsVectorizer()
        tfidf_matrix = vectorizer.fit_transform(news_items)
        keywords = vectorizer.get_top_keywords(tfidf_matrix, [0, 1, 2], n=5)
    """

    def __init__(self) -> None:
        """
        初始化向量化器

        配置说明：
            - tokenizer: 使用 jieba.lcut 进行中文分词
            - max_features: 最多保留 5000 个特征词
            - max_df: 忽略文档频率超过 85% 的词（过于常见的词）
            - min_df: 忽略出现次数少于 2 次的词（过于稀有的词）
            - stop_words: 使用自定义中文停用词表
        """
        # 预加载 jieba 词典，避免首次分词时的延迟
        jieba.initialize()
        logger.info("jieba 分词引擎初始化完成")

        # 构建 TF-IDF 向量化器
        self._vectorizer = TfidfVectorizer(
            tokenizer=jieba.lcut,
            max_features=5000,
            max_df=0.85,
            min_df=2,
            stop_words=list(CHINESE_STOP_WORDS),
            token_pattern=None,  # 使用自定义 tokenizer 时需要禁用默认正则
        )

        # 记录是否已经拟合过数据
        self._is_fitted: bool = False

        logger.info("NewsVectorizer 初始化完成（max_features=5000, max_df=0.85, min_df=2）")

    def fit_transform(self, news_items: list[dict]) -> spmatrix | None:
        """
        对新闻列表进行 TF-IDF 特征提取

        将每条新闻的标题和描述拼接为一个文本文档，然后进行向量化处理。

        Args:
            news_items: 新闻字典列表，每个字典至少包含 'title' 和 'description' 键。
                        示例: [{'title': '标题', 'description': '描述内容'}, ...]

        Returns:
            TF-IDF 稀疏矩阵，行为文档、列为特征词；
            如果输入为空或无有效文本，返回 None。
        """
        # 处理空输入
        if not news_items:
            logger.warning("fit_transform 收到空的新闻列表，返回 None")
            return None

        # 拼接标题和描述，生成文档列表
        documents: list[str] = []
        for item in news_items:
            title = item.get("title", "") or ""
            description = item.get("description", "") or ""
            # 标题和描述之间用空格分隔，保证分词不会粘连
            combined_text = f"{title} {description}".strip()
            documents.append(combined_text)

        # 过滤掉完全为空的文档
        if not any(doc.strip() for doc in documents):
            logger.warning("所有新闻文本均为空，无法进行向量化")
            return None

        logger.info("开始对 %d 篇新闻进行 TF-IDF 向量化...", len(documents))

        try:
            tfidf_matrix = self._vectorizer.fit_transform(documents)
            self._is_fitted = True
            logger.info(
                "TF-IDF 向量化完成：文档数=%d, 特征词数=%d",
                tfidf_matrix.shape[0],
                tfidf_matrix.shape[1],
            )
            return tfidf_matrix
        except ValueError as e:
            # 当所有词都被停用词或 min_df/max_df 过滤掉时会抛出 ValueError
            logger.error("TF-IDF 向量化失败：%s", e)
            return None

    def get_feature_names(self) -> list[str]:
        """
        获取特征词列表

        Returns:
            特征词名称列表，按照 TF-IDF 矩阵列的顺序排列。
            如果尚未拟合数据，返回空列表。
        """
        if not self._is_fitted:
            logger.warning("向量化器尚未拟合数据，无法获取特征词")
            return []

        return list(self._vectorizer.get_feature_names_out())

    def get_top_keywords(
        self,
        tfidf_matrix: spmatrix,
        indices: list[int],
        n: int = 5,
    ) -> list[str]:
        """
        从 TF-IDF 矩阵中提取指定行的 Top-N 关键词

        对给定行索引对应的 TF-IDF 向量求和，然后按得分降序排列，
        返回得分最高的 N 个关键词。

        Args:
            tfidf_matrix: TF-IDF 稀疏矩阵
            indices: 需要分析的行索引列表（对应新闻条目）
            n: 返回的关键词数量，默认为 5

        Returns:
            关键词列表，按 TF-IDF 得分从高到低排列。
            如果输入无效，返回空列表。
        """
        # 参数校验
        if tfidf_matrix is None or not indices:
            return []

        if not self._is_fitted:
            logger.warning("向量化器尚未拟合数据，无法提取关键词")
            return []

        try:
            feature_names = self.get_feature_names()
            if not feature_names:
                return []

            # 过滤有效索引，防止越界
            valid_indices = [i for i in indices if 0 <= i < tfidf_matrix.shape[0]]
            if not valid_indices:
                logger.warning("所有提供的索引均无效")
                return []

            # 取出指定行并按列求和，得到每个特征词的综合得分
            sub_matrix = tfidf_matrix[valid_indices]
            summed_scores = sub_matrix.sum(axis=0).A1  # 转换为一维数组

            # 按得分降序排列，取 Top-N
            top_indices = summed_scores.argsort()[::-1][:n]
            top_keywords = [
                feature_names[idx]
                for idx in top_indices
                if summed_scores[idx] > 0
            ]

            return top_keywords

        except Exception as e:
            logger.error("提取关键词时发生错误：%s", e)
            return []
