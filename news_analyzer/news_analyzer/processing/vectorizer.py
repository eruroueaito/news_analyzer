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
import re
from typing import Any

import jieba
from scipy.sparse import spmatrix
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS

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
    # 月份
    "一月", "二月", "三月", "四月", "五月", "六月",
    "七月", "八月", "九月", "十月", "十一月", "十二月",
    # 新闻叙事套话
    "表示", "指出", "称", "据", "报道", "消息", "相关",
    "发布", "发现", "发生", "认为", "表明", "显示", "宣布",
    "记者", "编辑", "编辑部", "文章", "内容", "方式", "目前",
    "少数派", "用户", "本文",
    # 标点符号及特殊字符（分词后可能残留）
    ".", ",", "!", "?", ";", ":", "'", '"', "(", ")",
    "。", "，", "！", "？", "；", "：", "'", "'", """, """,
    "（", "）", "【", "】", "《", "》", "、", "…", "——",
    "\n", "\t", " ", "\r",
}

# 通用英文非实体词（形容词、副词、高频动词、新闻套话等）
_GENERIC_ENGLISH_STOP_WORDS: set[str] = {
    # 形容词
    "new", "old", "big", "top", "best", "free", "good", "great", "high",
    "low", "long", "short", "open", "small", "large", "full", "real",
    "latest", "breaking", "major", "key", "hot", "live", "last", "next",
    "former", "current", "senior", "local", "national", "global",
    "political", "economic", "military", "federal", "public", "private",
    # 高频动词
    "says", "said", "say", "get", "got", "make", "made", "use", "used",
    "take", "took", "give", "gave", "come", "came", "look", "back",
    "goes", "went", "run", "running", "put", "puts", "keep", "kept",
    "show", "shows", "shown", "tell", "told", "call", "calls", "called",
    "need", "needs", "want", "wants", "help", "helps", "helped",
    "ask", "asks", "asked", "start", "starts", "started", "end", "ends",
    # 高频名词（新闻套话）
    "year", "years", "day", "days", "time", "times", "week", "weeks",
    "month", "months", "way", "part", "place", "case", "world", "report",
    "people", "man", "men", "woman", "women", "group", "set", "number",
    "plan", "plans", "deal", "deals", "move", "moves", "step", "steps",
    "news", "read", "more", "work", "works", "life", "home", "money",
    "power", "right", "rights", "law", "laws", "policy", "official",
    "officials", "leader", "leaders", "member", "members", "percent",
    # 助动词 / 系动词（sklearn ENGLISH_STOP_WORDS 未完全覆盖）
    "can", "has", "had", "was", "are", "were", "will", "may", "might",
    "been", "being", "did", "does", "just", "also", "even", "still",
    "now", "then", "here", "there", "how", "why", "who", "what",
    "when", "where", "which",
    # 月份全称
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
    # 月份缩写（3字母，通过过滤器但无意义）
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    # 星期全称
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    # 序数词
    "first", "second", "third", "fourth", "fifth", "sixth",
    "seventh", "eighth", "ninth", "tenth",
    # 数量词
    "million", "billion", "trillion", "hundred", "thousand",
    # 更多介词/连词/新闻套话
    "according", "amid", "ahead", "following", "including", "per",
    "via", "among", "without", "within", "against", "between",
    "around", "through", "despite", "while", "could", "would", "should",
    "let", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "many", "much", "few", "less", "more", "most",
    "every", "each", "any", "some", "other", "others", "own", "same",
    "after", "before", "over", "under", "than", "like", "want",
}

# 合并中文、sklearn 内置英文、通用英文停用词（模块级一次性计算）
ALL_STOP_WORDS: set[str] = CHINESE_STOP_WORDS | set(ENGLISH_STOP_WORDS) | _GENERIC_ENGLISH_STOP_WORDS
# 预先转为 list 供 TfidfVectorizer 使用（避免每次构造时重复转换）
_ALL_STOP_WORDS_LIST: list[str] = list(ALL_STOP_WORDS)

# 匹配「有意义的 token」：
#   - 中文词：至少 2 个汉字
#   - 英文词：至少 3 个字母（过滤 "a", "an", "is", "of" 等）
#   - 拒绝纯标点、HTML 实体、单字符、纯数字
_VALID_TOKEN_RE = re.compile(
    r'^(?:[\u4e00-\u9fff\u3400-\u4dbf]{2,}|[a-zA-Z]{3,})$'
)


def _tokenize(text: str) -> list[str]:
    """jieba 分词 + 垃圾 token 过滤"""
    # 预处理：去除 HTML 实体（&amp; &#160; 等）和多余空白
    text = re.sub(r'&[a-zA-Z]{2,6};|&#\d+;', ' ', text)
    tokens = jieba.lcut(text)
    result = []
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        # 只保留符合规则的 token（2+ 汉字 或 3+ 英文字母）
        if _VALID_TOKEN_RE.match(tok):
            # 英文词统一小写，使 America/american 等归一化
            result.append(tok.lower() if tok.isascii() else tok)
    return result


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
            tokenizer=_tokenize,
            max_features=5000,
            max_df=0.5,   # 出现在超过 50% 文档中的词视为通用词，过滤掉
            min_df=2,
            stop_words=_ALL_STOP_WORDS_LIST,
            token_pattern=None,  # 使用自定义 tokenizer 时需要禁用默认正则
        )

        # 记录是否已经拟合过数据
        self._is_fitted: bool = False

        logger.info("NewsVectorizer 初始化完成（max_features=5000, max_df=0.5, min_df=2）")

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
