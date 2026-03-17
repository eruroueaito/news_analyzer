"""
新闻数据存储

负责保存和加载新闻数据。
"""

import os
import json
import logging
import shutil
from datetime import datetime


class NewsStorage:
    """新闻数据存储类"""
    
    def __init__(self, data_dir="data"):
        """初始化存储器
        
        Args:
            data_dir: 数据存储目录
        """
        self.logger = logging.getLogger('news_analyzer.storage')
        
        # 跨平台数据目录：优先使用项目内相对路径，回退到用户主目录
        self.app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.app_root, data_dir)

        # 如果项目内路径不可用，使用用户主目录下的 .news_analyzer/data
        if not os.path.exists(self.data_dir):
            self.data_dir = os.path.abspath(data_dir)
        if not os.path.exists(self.data_dir):
            self.data_dir = os.path.join(os.path.expanduser("~"), ".news_analyzer", "data")
        
        # 确保目录存在
        self._ensure_dir(self.data_dir)
        self._ensure_dir(os.path.join(self.data_dir, "news"))
        self._ensure_dir(os.path.join(self.data_dir, "analysis"))
        
        self.logger.info(f"数据存储目录: {self.data_dir}")
    
    def _ensure_dir(self, directory):
        """确保目录存在
        
        Args:
            directory: 目录路径
        """
        if not os.path.exists(directory):
            os.makedirs(directory)
            self.logger.info(f"创建目录: {directory}")
    
    def save_news(self, news_items, filename=None):
        """保存新闻数据
        
        Args:
            news_items: 新闻条目列表
            filename: 文件名（可选，默认使用时间戳）
            
        Returns:
            str: 保存的文件路径
        """
        if not news_items:
            self.logger.warning("没有新闻数据可保存")
            return None
        
        # 如果没有指定文件名，使用时间戳
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"news_{timestamp}.json"
        
        filepath = os.path.join(self.data_dir, "news", filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"保存了 {len(news_items)} 条新闻到 {filepath}")
            return filepath
        
        except Exception as e:
            self.logger.error(f"保存新闻数据失败: {str(e)}")
            return None
    
    def load_news(self, filename=None):
        """加载新闻数据
        
        Args:
            filename: 文件名（可选，默认加载最新的文件）
            
        Returns:
            list: 新闻条目列表
        """
        # 如果没有指定文件名，加载最新的文件
        if not filename:
            files = self.list_news_files()
            if not files:
                self.logger.warning("没有找到新闻数据文件")
                return []
            
            filename = files[-1]  # 最新的文件
        
        filepath = os.path.join(self.data_dir, "news", filename)
        
        try:
            if not os.path.exists(filepath):
                self.logger.warning(f"文件不存在: {filepath}")
                return []
            
            with open(filepath, 'r', encoding='utf-8') as f:
                news_items = json.load(f)
            
            self.logger.info(f"从 {filepath} 加载了 {len(news_items)} 条新闻")
            return news_items
        
        except Exception as e:
            self.logger.error(f"加载新闻数据失败: {str(e)}")
            return []
    
    def save_today_news(self, news_items) -> str | None:
        """保存今日新闻缓存（固定文件名，每次覆盖）

        文件名格式：``news_today_YYYYMMDD.json``

        Args:
            news_items: 新闻条目列表

        Returns:
            str | None: 文件路径，失败返回 None
        """
        if not news_items:
            return None
        today = datetime.now().strftime("%Y%m%d")
        filename = f"news_today_{today}.json"
        filepath = os.path.join(self.data_dir, "news", filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(news_items, f, ensure_ascii=False, indent=2)
            self.logger.info(f"保存今日缓存：{len(news_items)} 条 → {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"保存今日缓存失败: {e}")
            return None

    def load_today_news(self) -> list:
        """加载今日新闻缓存

        Returns:
            list: 今日已缓存的新闻条目列表，若无则返回空列表
        """
        today = datetime.now().strftime("%Y%m%d")
        filename = f"news_today_{today}.json"
        filepath = os.path.join(self.data_dir, "news", filename)
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                items = json.load(f)
            self.logger.info(f"加载今日缓存：{len(items)} 条 ← {filepath}")
            return items
        except Exception as e:
            self.logger.error(f"加载今日缓存失败: {e}")
            return []

    def cleanup_old_today_cache(self, keep_days: int = 3):
        """清理超过 keep_days 天的旧今日缓存文件

        Args:
            keep_days: 保留最近几天的缓存（默认 3 天）
        """
        news_dir = os.path.join(self.data_dir, "news")
        if not os.path.exists(news_dir):
            return
        try:
            cutoff = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            import datetime as dt
            cutoff -= dt.timedelta(days=keep_days)
            cutoff_str = cutoff.strftime("%Y%m%d")

            for fname in os.listdir(news_dir):
                if not fname.startswith("news_today_") or not fname.endswith(".json"):
                    continue
                # 提取日期部分：news_today_YYYYMMDD.json
                date_part = fname[len("news_today_"):-len(".json")]
                if len(date_part) == 8 and date_part < cutoff_str:
                    try:
                        os.remove(os.path.join(news_dir, fname))
                        self.logger.info(f"清理旧缓存: {fname}")
                    except Exception as e:
                        self.logger.warning(f"删除旧缓存文件失败 {fname}: {e}")
        except Exception as e:
            self.logger.error(f"清理旧缓存失败: {e}")

    def list_news_files(self):
        """列出所有新闻文件
        
        Returns:
            list: 文件名列表，按日期排序
        """
        news_dir = os.path.join(self.data_dir, "news")
        if not os.path.exists(news_dir):
            self.logger.warning(f"新闻目录不存在: {news_dir}")
            return []
        
        try:
            files = [f for f in os.listdir(news_dir) if f.endswith('.json')]
            return sorted(files)
        except Exception as e:
            self.logger.error(f"列出新闻文件失败: {str(e)}")
            return []