from datetime import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.firefox import GeckoDriverManager
from airbnb_calendar_checker import check_calendar_availability, export_to_excel
from price_checker import check_room_price
from logger_config import get_logger
import re
import os
import traceback
import time
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import requests
import hmac
import hashlib
import base64
import shutil
from bit_browser_manager import BitBrowserManager
import threading

# 在文件顶部添加配置变量
MAX_CONCURRENT_THREADS = 3  # 最大并发线程数
GECKODRIVER_VERSION = "v0.33.0"  # 指定版本
GECKODRIVER_PATH = os.path.join(os.path.dirname(__file__), "drivers", "geckodriver.exe")
GECKODRIVER_URL = "https://github.com/mozilla/geckodriver/releases/download/v0.33.0/geckodriver-v0.33.0-win64.zip"

class KookeeyProxy:
    def __init__(self):
        self.access_id = "7731224"
        self.secret_key = "565067ae9400a1f722e83918c510c829"
        self.session = requests.session()
        
    def get_proxy(self):
        """获取代理IP"""
        logger = get_logger()
        try:
            # 获取时间戳
            ts = str(int(time.time()))
            
            # 构建参数字符串
            param_str = f"p=http&ts={ts}"
            
            # 计算签名
            token = base64.b64encode(
                hmac.new(
                    bytes(self.secret_key, encoding='utf-8'),
                    bytes(param_str, encoding='utf-8'),
                    hashlib.sha1
                ).hexdigest().encode('utf-8')
            ).decode('utf-8')
            
            # 构建API URL
            api_url = (
                f"https://kookeey.com/ip?"
                f"accessid={self.access_id}&"
                f"signature={token}&"
                f"{param_str}"
            )
            
            # 发送请求
            response = self.session.get(api_url, verify=False, timeout=30)
            
            if response.status_code == 200:
                proxy_info = response.text.strip()
                logger.info(f"成功获取代理IP: {proxy_info}")
                return proxy_info
            else:
                logger.error(f"获取代理IP失败: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"获取代理IP时发生错误: {e}")
            return None

def read_room_ids(filename='RoomID.xlsx'):
    """读取房间ID"""
    logger = get_logger()
    try:
        if not os.path.exists(filename):
            logger.error(f"文件不存在: {filename}")
            return None
            
        # 读取Excel文件，将第一列作为字符串读取
        df = pd.read_excel(filename, dtype={0: str})  # 指定第一列为字符串类型
        
        # 获取房间ID列表，确保是字符串格式
        room_ids = []
        for _, row in df.iterrows():
            room_id = str(row.iloc[0]).strip()  # 转换为字符串并去除空白
            if pd.notna(row.iloc[0]) and room_id:  # 检查是否为空
                # 移除可能的小数点和科学计数法
                room_id = room_id.split('.')[0]  # 移除小数部分
                room_id = room_id.split('E')[0]  # 移除科学计数法部分
                room_ids.append(room_id)
                logger.debug(f"读取到房间ID: {room_id}")
        
        logger.info(f"成功读取 {len(room_ids)} 个房间ID")
        if room_ids:
            logger.debug(f"房间ID示例: {room_ids[0]}")
        
        return room_ids
        
    except Exception as e:
        logger.error(f"读取房间信息时发生错误: {str(e)}")
        logger.error(f"错误类型: {type(e).__name__}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return None

def generate_urls(room_ids):
    """根房间ID生成URL列表"""
    base_url = "https://www.airbnb.co.nz/rooms/"
    urls = []
    logger = get_logger()
    
    for room_id in room_ids:
        url = {'url': base_url + room_id}
        logger.debug(f"生成URL: {url['url']}")
        urls.append(url)
    
    return urls

def create_data_directory():
    """创建数据存储目录"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    data_dir = f'data/airbnb_data_{timestamp}'
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def download_geckodriver():
    """直接下载GeckoDriver"""
    logger = get_logger()
    try:
        import urllib.request
        import zipfile
        import tempfile
        
        # 创建drivers目录
        os.makedirs(os.path.dirname(GECKODRIVER_PATH), exist_ok=True)
        
        # 如果已存在，直接返回
        if os.path.exists(GECKODRIVER_PATH):
            logger.info("GeckoDriver已存在")
            return True
            
        # 下载文件
        logger.info(f"正在从 {GECKODRIVER_URL} 下载GeckoDriver...")
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, "geckodriver.zip")
        
        urllib.request.urlretrieve(GECKODRIVER_URL, zip_path)
        
        # 解压文件
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extract("geckodriver.exe", os.path.dirname(GECKODRIVER_PATH))
            
        logger.info(f"GeckoDriver已下载并解压到: {GECKODRIVER_PATH}")
        return True
        
    except Exception as e:
        logger.error(f"下载GeckoDriver失败: {e}")
        return False

def initialize_driver(max_retries=3):
    """初始化BitBrowser WebDriver"""
    logger = get_logger()
    logger.info("开始初始化BitBrowser...")
    
    try:
        browser_manager = BitBrowserManager()
        
        # 直接连接到浏览器
        driver = browser_manager.connect_browser()
        if not driver:
            logger.error("连接BitBrowser失败")
            return None
            
        # 设置超时时间
        driver.set_page_load_timeout(60)
        driver.implicitly_wait(20)
        
        # 存储browser_manager用于后续清理
        driver.browser_manager = browser_manager
        
        return driver
        
    except Exception as e:
        logger.error(f"初始化BitBrowser失败: {e}")
        return None

def analyze_listing(url_info, driver):
    """分析单个房源"""
    logger = get_logger()
    url = url_info['url']
    logger.info(f"\n开始分析房源: {url}")
    
    try:
        # 1. 获取日历数据
        calendar_data, excel_file, driver = check_calendar_availability(url, driver)
        if not calendar_data:
            logger.error(f"获取日历数据失败: {url}")
            return None
            
        logger.info(f"成功获取日历数据: {len(calendar_data)} 条记录")
        
        # 2. 获取价格数据
        price_info = check_room_price(url_info, calendar_data, driver)
        if not price_info:
            logger.error(f"获取格数据失败: {url}")
        else:
            logger.info("成功获取价格数据")
        
        # 3. 合并数据
        result = {
            'url': url,
            'calendar_data': calendar_data,
            'price_info': price_info,
            'calendar_excel': excel_file
        }
        
        return result
        
    except Exception as e:
        logger.error(f"分析房源时发生错误: {str(e)}")
        return None

def analyze_multiple_listings(urls):
    """并发分析多个房源"""
    logger = get_logger()
    logger.info("=== 开始批量分析房源 ===")
    
    # 创建时间戳目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    date_dir = f'data/{timestamp}'
    os.makedirs(date_dir, exist_ok=True)
    
    results = []
    max_workers = min(MAX_CONCURRENT_THREADS, len(urls))
    logger.info(f"设置并发线程数: {max_workers}")

    try:
        browser_manager = BitBrowserManager()
        
        # 获取所有可用的浏览器实例
        browsers = browser_manager.get_all_browsers()
        if not browsers:
            logger.error("没有可用的浏览器实例")
            return []
            
        # 确保有足够的浏览器实例
        if len(browsers) < max_workers:
            logger.warning(f"可用浏览器实例数量({len(browsers)})小于线程数({max_workers})")
            max_workers = len(browsers)
            
        logger.info("\n=== 可用的浏览器实例 ===")
        for browser in browsers[:max_workers]:
            logger.info(f"ID: {browser['id']}")
            logger.info(f"名称: {browser['name']}")
            logger.info(f"备注: {browser['remark']}")
            logger.info(f"PID: {browser['pid']}\n")
            
        # 将URLs平均分配给每个线程
        urls_per_thread = len(urls) // max_workers
        remainder = len(urls) % max_workers
        
        url_chunks = []
        start = 0
        for i in range(max_workers):
            # 如果有余数，前几个线程多分配一个URL
            chunk_size = urls_per_thread + (1 if i < remainder else 0)
            end = start + chunk_size
            url_chunks.append(urls[start:end])
            start = end
            
        logger.info("\n=== URL分配情况 ===")
        for i, chunk in enumerate(url_chunks):
            logger.info(f"线程 {i+1} 分配到 {len(chunk)} 个URL:")
            for url in chunk:
                room_id = url['url'].split('rooms/')[-1].split('?')[0]
                logger.info(f"  - Room ID: {room_id}")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            
            # 为每个线程分配一个浏览器实例和一组URL
            for i, (browser, urls_chunk) in enumerate(zip(browsers[:max_workers], url_chunks)):
                browser_id = browser['id']
                
                def process_urls(urls_chunk, browser_id, thread_index):
                    thread_id = threading.get_ident()
                    logger.info(f"线程 {thread_id} (#{thread_index+1}) 使用浏览器 {browser_id}")
                    thread_results = []
                    
                    try:
                        # 连接到指定的浏览器实例
                        driver = browser_manager.connect_browser(browser_id=browser_id)
                        if not driver:
                            logger.error(f"无法连接到浏览器实例 {browser_id}")
                            return None
                            
                        # 处理分配给这个线程的所有URL
                        for url_info in urls_chunk:
                            room_id = url_info['url'].split('rooms/')[-1].split('?')[0]
                            logger.info(f"线程 #{thread_index+1} 开始处理 Room ID: {room_id}")
                            
                            try:
                                # 在新标签页中打开URL
                                result = browser_manager.open_url_in_new_tab(driver, url_info['url'])
                                if not result:
                                    logger.error(f"无法在浏览器 {browser_id} 中打开URL {url_info['url']}")
                                    continue
                                    
                                # 分析房源
                                result = analyze_listing(url_info, driver)
                                if result:
                                    thread_results.append(result)
                                    logger.info(f"线程 #{thread_index+1} 完成 Room ID: {room_id}")
                                
                                # 关闭标签页但保持浏览器实例
                                browser_manager.close_tab(driver)
                                
                            except Exception as e:
                                logger.error(f"处理 Room ID {room_id} 时发生错误: {str(e)}")
                                continue
                                
                        return thread_results
                        
                    except Exception as e:
                        logger.error(f"线程 #{thread_index+1} 发生错误: {str(e)}")
                        return None

                futures.append(executor.submit(process_urls, urls_chunk, browser_id, i))

            # 收集所有线程的结果
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                try:
                    thread_results = future.result()
                    if thread_results:
                        results.extend(thread_results)
                        # 处理每个结果...
                        for result in thread_results:
                            # 复制文件等操作...
                            room_id = result['url'].split('rooms/')[-1].split('?')[0]
                            room_dir = f'data/room_{room_id}'
                            os.makedirs(room_dir, exist_ok=True)
                            
                            # 复制到日期目录和房间目录
                            # ... 其余代码保持不变 ...
                            
                except Exception as e:
                    logger.error(f"处理线程 {i+1} 的结果时发生错误: {str(e)}")

        return results
        
    except Exception as e:
        logger.error(f"批量分析过程中发生错误: {str(e)}")
        return results

def create_summary_data(results):
    """创建汇总数据"""
    summary_data = []
    for result in results:
        if result:
            room_id = result['url'].split('rooms/')[-1]
            
            # 基础信息
            summary_info = {
                'Room ID': room_id,
                'URL': result['url'],
                '总天数': len(result['calendar_data']),
                '可预订天数': sum(1 for d in result['calendar_data'] if d['status'] == "可预订"),
                '不可预订天数': sum(1 for d in result['calendar_data'] if d['status'] == "不可预订"),
                '数据文件': result['calendar_excel']
            }
            
            # 添加价格统计
            if result['price_info'] and isinstance(result['price_info'], list):
                prices = [float(re.search(r'\$(\d+)', p['nightly_price']).group(1)) 
                         for p in result['price_info'] if p['nightly_price']]
                if prices:
                    summary_info.update({
                        '平均每晚价格': f"${sum(prices)/len(prices):.2f}",
                        '最高每晚价格': f"${max(prices):.2f}",
                        '最低每晚价格': f"${min(prices):.2f}",
                        '价格样本数': len(prices)
                    })
            
            summary_data.append(summary_info)
    return summary_data

def main():
    logger = get_logger()
    logger.info("=== 开始Airbnb数据收集程序 ===")
    
    try:
        # 1. 读取房间ID
        room_ids = read_room_ids()
        if not room_ids:
            logger.error("未能读取房间信息，程序退出")
            return
            
        # 2. 生成URL列表
        urls = generate_urls(room_ids)
        logger.info(f"生成 {len(urls)} 个URL")
        
        # 3. 创建数据存储目录
        data_dir = create_data_directory()
        logger.info(f"创建数据目录: {data_dir}")
        
        # 4. 执行数据收集
        results = analyze_multiple_listings(urls)
        
        # 5. 生成汇总报告
        if results:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            summary_file = f'{data_dir}/airbnb_summary_{timestamp}.xlsx'
            
            # 创建汇总数据
            summary_data = []
            for result in results:
                if result:  # 确保结果有效
                    room_id = result['url'].split('rooms/')[-1]
                    
                    # 基础信息
                    summary_info = {
                        'Room ID': room_id,
                        'URL': result['url'],
                        '总天数': len(result['calendar_data']),
                        '可预订天数': sum(1 for d in result['calendar_data'] if d['status'] == "可预订"),
                        '不可预订天数': sum(1 for d in result['calendar_data'] if d['status'] == "不可预订"),
                        '数据文件': result['calendar_excel']
                    }
                    
                    # 添加价格统计
                    if result['price_info'] and isinstance(result['price_info'], list):
                        prices = [float(re.search(r'\$(\d+)', p['nightly_price']).group(1)) 
                                for p in result['price_info'] if p['nightly_price']]
                        if prices:
                            summary_info.update({
                                '平均每晚价格': f"${sum(prices)/len(prices):.2f}",
                                '最高每晚价格': f"${max(prices):.2f}",
                                '最低每晚价格': f"${min(prices):.2f}",
                                '价格样本数': len(prices)
                            })
                    
                    summary_data.append(summary_info)
            
            # 保存汇总报告
            if summary_data:
                pd.DataFrame(summary_data).to_excel(summary_file, index=False)
                logger.info(f"汇总报告已保存到: {summary_file}")
                
                # 打印统计信息
                print("\n=== 数据收集完成 ===")
                print(f"总房源数: {len(room_ids)}")
                print(f"成功收集: {len(summary_data)}")
                print(f"失败数量: {len(room_ids) - len(summary_data)}")
                print(f"汇总报告: {summary_file}")
        
    except Exception as e:
        logger.error(f"程序执行过程中发生错误: {str(e)}")
    finally:
        logger.info("=== 程序执行完成 ===")

if __name__ == "__main__":
    main()