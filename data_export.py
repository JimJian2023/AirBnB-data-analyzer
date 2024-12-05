import os
import pandas as pd
import traceback
from datetime import datetime
from logger_config import get_logger

class DataExporter:
    """数据导出管理类"""
    
    def __init__(self, config=None):
        """
        初始化数据导出器
        config: 可选的配置字典，用于覆盖默认配置
        """
        self.logger = get_logger()
        
        # 默认配置
        self.default_config = {
            'base_dir': 'data',
            'subdirs': {
                'date': 'by_date',
                'room': 'by_room'
            },
            'file_prefix': {
                'calendar': 'calendar',
                'price': 'price',
                'summary': 'summary'
            },
            'required_fields': {
                'calendar': ['date', 'status', 'is_blocked'],
                'price': ['date', 'price', 'currency'],
                'summary': ['Room ID', 'URL']
            }
        }
        
        # 合并自定义配置
        self.config = {**self.default_config, **(config or {})}
        
        # 构建完整的目录路径
        self.base_dirs = {
            'date': os.path.join(self.config['base_dir'], self.config['subdirs']['date']),
            'room': os.path.join(self.config['base_dir'], self.config['subdirs']['room'])
        }
        
        # 初始化目录结构
        self._init_directories()

    def _init_directories(self):
        """初始化目录结构"""
        try:
            # 创建基础目录
            os.makedirs(self.config['base_dir'], exist_ok=True)
            self.logger.info(f"创建基础目录: {self.config['base_dir']}")
            
            # 创建子目录
            for dir_name, dir_path in self.base_dirs.items():
                os.makedirs(dir_path, exist_ok=True)
                self.logger.info(f"创建{dir_name}目录: {dir_path}")
                
        except Exception as e:
            self.logger.error(f"创建目录结构时发生错误: {str(e)}")
            self.logger.error(traceback.format_exc())
            raise

    def _get_room_id(self, url):
        """从URL中提取房间ID"""
        try:
            return url.split('rooms/')[-1].split('?')[0]
        except Exception as e:
            self.logger.error(f"从URL提取房间ID时发生错误: {str(e)}")
            return None

    def _validate_and_clean_data(self, data, data_type):
        """
        验证和清理数据
        data: 要验证的数据
        data_type: 数据类型 (calendar/price/summary)
        """
        try:
            if not data:
                self.logger.warning(f"收到空的{data_type}数据")
                return None
                
            # 确保数据是列表形式
            if not isinstance(data, list):
                data = [data]
                
            # 移除空记录
            data = [item for item in data if item]
            
            # 检查必要字段
            required_fields = self.config['required_fields'].get(data_type, [])
            for item in data:
                if not all(field in item for field in required_fields):
                    self.logger.warning(f"{data_type}数据缺少必要字段: {required_fields}")
                    return None
                    
            return data
            
        except Exception as e:
            self.logger.error(f"数据验证时发生错误: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None

    def _export_data(self, data, data_type, url=None, additional_info=None):
        """
        通用数据导出函数
        data: 要导出的数据
        data_type: 数据类型
        url: 房源URL（可选）
        additional_info: 额外信息（可选）
        """
        try:
            # 生成时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 验证和清理数据
            cleaned_data = self._validate_and_clean_data(data, data_type)
            if cleaned_data is None:
                return None
                
            # 准备文件名
            prefix = self.config['file_prefix'][data_type]
            room_id = self._get_room_id(url) if url else 'unknown'
            
            # 构建文件路径
            date_file = os.path.join(self.base_dirs['date'], f'{prefix}_{room_id}_{timestamp}.xlsx')
            room_file = os.path.join(self.base_dirs['room'], room_id, f'{prefix}_{timestamp}.xlsx') if room_id != 'unknown' else None
            
            # 创建DataFrame
            df = pd.DataFrame(cleaned_data)
            
            # 添加额外信息
            if additional_info:
                for key, value in additional_info.items():
                    df[key] = value
            
            # 保存文件
            df.to_excel(date_file, index=False)
            self.logger.info(f"{data_type}数据已导出到日期目录: {date_file}")
            
            if room_file:
                os.makedirs(os.path.dirname(room_file), exist_ok=True)
                df.to_excel(room_file, index=False)
                self.logger.info(f"{data_type}数据已导出到房间目录: {room_file}")
            
            return {
                'date_file': date_file,
                'room_file': room_file,
                'timestamp': timestamp,
                'room_id': room_id
            }
            
        except Exception as e:
            self.logger.error(f"导出{data_type}数据时发生错误: {str(e)}")
            self.logger.error(traceback.format_exc())
            return None

    def export_calendar_data(self, calendar_data, url):
        """导出日历数据"""
        return self._export_data(calendar_data, 'calendar', url)

    def export_price_data(self, price_data, url):
        """导出价格数据"""
        return self._export_data(price_data, 'price', url)

    def export_summary_data(self, summary_data):
        """导出汇总数据"""
        result = self._export_data(summary_data, 'summary')
        if result:
            print("\n=== 数据收集完成 ===")
            print(f"总记录数: {len(summary_data)}")
            print(f"汇总报告: {result['date_file']}")
        return result

# 提供一个便捷的全局实例
exporter = DataExporter() 