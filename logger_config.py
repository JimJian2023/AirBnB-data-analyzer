import logging
import os
from datetime import datetime

class LoggerConfig:
    _instance = None
    _logger = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerConfig, cls).__new__(cls)
            cls._setup_logger()
        return cls._instance
    
    @classmethod
    def _setup_logger(cls):
        """设置日志记录器"""
        # 创建logs目录（如果不存在）
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        # 生成日志文件名（使用时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f'logs/airbnb_analysis_{timestamp}.log'
        
        # 创建日志记录器
        cls._logger = logging.getLogger('AirbnbAnalysis')
        cls._logger.setLevel(logging.INFO)
        
        # 创建文件处理器
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s'
        )
        
        # 设置格式化器
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        cls._logger.addHandler(file_handler)
        cls._logger.addHandler(console_handler)
    
    @classmethod
    def get_logger(cls):
        """获取日志记录器实例"""
        if cls._logger is None:
            cls._setup_logger()
        return cls._logger

# 提供一个便捷的函数来获取logger
def get_logger():
    return LoggerConfig.get_logger() 