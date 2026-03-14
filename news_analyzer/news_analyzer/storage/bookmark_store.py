#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
书签持久化存储模块 - 管理用户收藏的关键词书签

该模块实现了 BookmarkStore 类，提供关键词书签的增删查改及 JSON 持久化功能。
书签数据以 JSON 格式存储在指定的数据目录下。
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class BookmarkStore:
    """
    书签持久化存储

    将用户收藏的关键词书签保存到 JSON 文件中，
    支持添加、删除、查询和判断是否已收藏等操作。
    """

    def __init__(self, data_dir: str):
        """
        初始化书签存储

        Args:
            data_dir: 数据存储根目录，书签文件将保存在 data_dir/data/bookmarks.json
        """
        # 构建书签文件的完整路径
        self._data_dir = os.path.join(data_dir, "data")
        self._file_path = os.path.join(self._data_dir, "bookmarks.json")

        # 内存中的书签列表，每个元素为 {"keyword": str, "added_at": str}
        self._bookmarks: list[dict] = []

        # 确保数据目录存在
        os.makedirs(self._data_dir, exist_ok=True)

        # 从磁盘加载已有书签
        self._load()

    def add_bookmark(self, keyword: str) -> None:
        """
        添加关键词书签

        如果该关键词尚未被收藏，则添加并保存。
        已存在的关键词不会重复添加。

        Args:
            keyword: 要收藏的关键词
        """
        # 规范化关键词：去除首尾空白
        keyword = keyword.strip()
        if not keyword:
            logger.warning("尝试添加空关键词书签，已忽略")
            return

        # 检查是否已存在
        if self.is_bookmarked(keyword):
            logger.debug("关键词 '%s' 已在书签列表中，跳过添加", keyword)
            return

        # 记录添加时间（ISO 8601 格式，UTC 时区）
        bookmark_entry = {
            "keyword": keyword,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self._bookmarks.append(bookmark_entry)
        self._save()
        logger.info("已添加书签: '%s'", keyword)

    def remove_bookmark(self, keyword: str) -> None:
        """
        移除关键词书签

        Args:
            keyword: 要移除的关键词
        """
        keyword = keyword.strip()
        original_count = len(self._bookmarks)

        # 过滤掉匹配的关键词（不区分大小写比较）
        self._bookmarks = [
            bm for bm in self._bookmarks
            if bm.get("keyword", "").lower() != keyword.lower()
        ]

        if len(self._bookmarks) < original_count:
            self._save()
            logger.info("已移除书签: '%s'", keyword)
        else:
            logger.debug("关键词 '%s' 不在书签列表中，无需移除", keyword)

    def get_bookmarks(self) -> list[dict]:
        """
        获取所有书签

        Returns:
            书签列表，每个元素包含 keyword 和 added_at 字段。
            返回的是副本，修改不会影响内部数据。
        """
        # 返回深拷贝，防止外部修改内部数据
        return [dict(bm) for bm in self._bookmarks]

    def is_bookmarked(self, keyword: str) -> bool:
        """
        判断关键词是否已被收藏

        比较时不区分大小写。

        Args:
            keyword: 要查询的关键词

        Returns:
            如果已收藏则返回 True
        """
        keyword_lower = keyword.strip().lower()
        return any(
            bm.get("keyword", "").lower() == keyword_lower
            for bm in self._bookmarks
        )

    def _save(self) -> None:
        """
        将书签数据持久化到 JSON 文件

        写入时使用临时文件 + 重命名策略，确保原子写入，
        避免写入过程中崩溃导致数据损坏。
        """
        temp_path = self._file_path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"bookmarks": self._bookmarks},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            # 原子替换：先写临时文件，再重命名
            os.replace(temp_path, self._file_path)
            logger.debug("书签数据已保存到 %s", self._file_path)
        except OSError as e:
            logger.error("保存书签文件失败: %s", e)
            # 清理可能残留的临时文件
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        except (TypeError, ValueError) as e:
            logger.error("序列化书签数据失败: %s", e)

    def _load(self) -> None:
        """
        从 JSON 文件加载书签数据

        如果文件不存在或内容损坏，则初始化为空列表。
        """
        if not os.path.exists(self._file_path):
            logger.debug("书签文件不存在，将使用空列表: %s", self._file_path)
            self._bookmarks = []
            return

        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 验证数据结构
            if isinstance(data, dict) and "bookmarks" in data:
                raw_bookmarks = data["bookmarks"]
                if isinstance(raw_bookmarks, list):
                    # 逐条验证并过滤无效条目
                    validated = []
                    for item in raw_bookmarks:
                        if (
                            isinstance(item, dict)
                            and "keyword" in item
                            and "added_at" in item
                            and isinstance(item["keyword"], str)
                            and isinstance(item["added_at"], str)
                        ):
                            validated.append({
                                "keyword": item["keyword"],
                                "added_at": item["added_at"],
                            })
                        else:
                            logger.warning("跳过无效的书签条目: %s", item)
                    self._bookmarks = validated
                    logger.info(
                        "已从文件加载 %d 条书签", len(self._bookmarks)
                    )
                    return

            # 数据结构不符合预期
            logger.warning("书签文件格式异常，将重置为空列表: %s", self._file_path)
            self._bookmarks = []

        except json.JSONDecodeError as e:
            logger.error("解析书签 JSON 文件失败: %s", e)
            self._bookmarks = []
        except OSError as e:
            logger.error("读取书签文件失败: %s", e)
            self._bookmarks = []
