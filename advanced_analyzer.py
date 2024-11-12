from datetime import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from airbnb_calendar_checker import check_calendar_availability, export_to_excel
from price_checker import check_room_price
from logger_config import get_logger
import re
import os
import traceback

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
    """根据房间ID生成URL列表"""
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

def initialize_driver():
    """初始化WebDriver"""
    logger = get_logger()
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    logger.info("Chrome WebDriver 初始化成功")
    return driver

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
            logger.error(f"获取价格数据失败: {url}")
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
    """分析多个房源"""
    logger = get_logger()
    logger.info("=== 开始批量分析房源 ===")
    
    # 创建时间戳目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    date_dir = f'data/{timestamp}'
    os.makedirs(date_dir, exist_ok=True)
    
    # 初始化WebDriver
    driver = initialize_driver()
    results = []
    
    try:
        for i, url in enumerate(urls, 1):
            logger.info(f"\n处理第 {i}/{len(urls)} 个房源")
            result = analyze_listing(url, driver)
            if result:
                results.append(result)
                
                # 复制日历数据到两个位置
                room_id = url['url'].split('rooms/')[-1].split('?')[0]
                room_dir = f'data/room_{room_id}'
                os.makedirs(room_dir, exist_ok=True)
                
                # 复制到日期目录
                date_calendar_file = f'{date_dir}/airbnb_calendar_{room_id}.xlsx'
                pd.read_excel(result['calendar_excel']).to_excel(date_calendar_file, index=False)
                
                # 复制到房间目录
                room_calendar_file = f'{room_dir}/airbnb_calendar_{timestamp}.xlsx'
                pd.read_excel(result['calendar_excel']).to_excel(room_calendar_file, index=False)
                
                logger.info(f"数据已保存到日期目录: {date_calendar_file}")
                logger.info(f"数据已保存到房间目录: {room_calendar_file}")
        
        # 生成汇总Excel，同样保存两份
        if results:
            summary_data = create_summary_data(results)
            
            # 保存到日期目录
            date_summary_file = f'{date_dir}/airbnb_summary.xlsx'
            pd.DataFrame(summary_data).to_excel(date_summary_file, index=False)
            
            # 保存到每个房间目录
            for result in results:
                room_id = result['url'].split('rooms/')[-1].split('?')[0]
                room_summary_file = f'data/room_{room_id}/airbnb_summary_{timestamp}.xlsx'
                
                # 只保存该房间的汇总数据
                room_summary = [d for d in summary_data if str(d['Room ID']) == room_id]
                if room_summary:
                    pd.DataFrame(room_summary).to_excel(room_summary_file, index=False)
            
            logger.info(f"汇总数据已保存到日期目录: {date_summary_file}")
            logger.info("汇总数据已保存到各房间目录")
        
        return results
        
    except Exception as e:
        logger.error(f"批量分析过程中发生错误: {str(e)}")
        return results
    finally:
        driver.quit()
        logger.info("浏览器已关闭")

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