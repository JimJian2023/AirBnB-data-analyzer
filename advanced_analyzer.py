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

def read_room_ids(filename='RoomID.xlsx'):
    """读取房间ID和最小入住天数"""
    logger = get_logger()
    try:
        if not os.path.exists(filename):
            logger.error(f"文件不存在: {filename}")
            return None
            
        # 读取Excel文件
        df = pd.read_excel(filename)
        
        # 获取房间ID和最小入住天数
        room_data = []
        for _, row in df.iterrows():
            room_info = {
                'room_id': str(row.iloc[0]),  # 第一列是房间ID
                'min_nights': int(row.iloc[1]) # 第二列是最小入住天数
            }
            room_data.append(room_info)
        
        logger.info(f"成功读取 {len(room_data)} 个房间信息")
        return room_data
        
    except Exception as e:
        logger.error(f"读取房间信息时发生错误: {str(e)}")
        return None

def generate_urls(room_data):
    """根据房间信息生成URL列表"""
    base_url = "https://www.airbnb.co.nz/rooms/"
    return [{
        'url': base_url + str(room['room_id']),
        'min_nights': room['min_nights']
    } for room in room_data]

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
    min_nights = url_info['min_nights']
    logger.info(f"\n开始分析房源: {url} (最小入住: {min_nights}晚)")
    
    try:
        # 1. 获取日历数据
        calendar_data, excel_file, driver = check_calendar_availability(url, driver)
        if not calendar_data:
            logger.error(f"获取日历数据失败: {url}")
            return None
            
        logger.info(f"成功获取日历数据: {len(calendar_data)} 条记录")
        
        # 2. 获取价格数据，传入包含最小入住天数的url_info
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
        
        # 4. 生成统计信息
        status_count = {}
        for date_info in calendar_data:
            status = date_info['status']
            status_count[status] = status_count.get(status, 0) + 1
            
        logger.info("\n=== 日历统计信息 ===")
        for status, count in status_count.items():
            percentage = (count / len(calendar_data)) * 100
            logger.info(f"{status}: {count}天 ({percentage:.2f}%)")
        
        return result
        
    except Exception as e:
        logger.error(f"分析房源时发生错误: {str(e)}")
        return None

def analyze_multiple_listings(urls):
    """分析多个房源"""
    logger = get_logger()
    logger.info("=== 开始批量分析房源 ===")
    
    # 初始化WebDriver
    driver = initialize_driver()
    results = []
    
    try:
        for i, url in enumerate(urls, 1):
            logger.info(f"\n处理第 {i}/{len(urls)} 个房源")
            result = analyze_listing(url, driver)
            if result:
                results.append(result)
                logger.info(f"数据已保存到: {result['calendar_excel']}")
                
        logger.info(f"\n分析完成，成功处理 {len(results)}/{len(urls)} 个房源")
        
        # 生成汇总Excel
        if results:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            summary_file = f'data/airbnb_summary_{timestamp}.xlsx'
            
            # 创建汇总数据
            summary_data = []
            for result in results:
                # 基础信息
                summary_info = {
                    'URL': result['url'],
                    '总天数': len(result['calendar_data']),
                    '可预订天数': sum(1 for d in result['calendar_data'] if d['status'] == "可预订"),
                    '不可预订天数': sum(1 for d in result['calendar_data'] if d['status'] == "不可预订"),
                    '仅可退房天数': sum(1 for d in result['calendar_data'] if d['status'] == "仅可退房"),
                    '数据文件': result['calendar_excel']
                }
                
                # 添加价格统计信息
                if result['price_info'] and isinstance(result['price_info'], list):
                    # 计算价格统计
                    nightly_prices = []
                    for price_item in result['price_info']:
                        try:
                            price = float(re.search(r'\$(\d+)', price_item['nightly_price']).group(1))
                            nightly_prices.append(price)
                        except:
                            continue
                    
                    if nightly_prices:
                        summary_info.update({
                            '平均每晚价格': f"${sum(nightly_prices)/len(nightly_prices):.2f}",
                            '最高每晚价格': f"${max(nightly_prices):.2f}",
                            '最低每晚价格': f"${min(nightly_prices):.2f}",
                            '价格样本数': len(nightly_prices)
                        })
                
                summary_data.append(summary_info)
            
            # 保存汇总Excel
            pd.DataFrame(summary_data).to_excel(summary_file, index=False)
            logger.info(f"汇总数据已保存到: {summary_file}")
        
        return results
        
    except Exception as e:
        logger.error(f"批量分析过程中发生错误: {str(e)}")
        return results
        
    finally:
        driver.quit()
        logger.info("浏览器已关闭")

def main():
    logger = get_logger()
    logger.info("=== 开始Airbnb数据收集程序 ===")
    
    try:
        # 1. 读取房间ID
        room_data = read_room_ids()
        if not room_data:
            logger.error("未能读取房间信息，程序退出")
            return
            
        # 2. 生成URL列表
        urls = generate_urls(room_data)
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
                print(f"总房源数: {len(room_data)}")
                print(f"成功收集: {len(summary_data)}")
                print(f"失败数量: {len(room_data) - len(summary_data)}")
                print(f"汇总报告: {summary_file}")
        
    except Exception as e:
        logger.error(f"程序执行过程中发生错误: {str(e)}")
    finally:
        logger.info("=== 程序执行完成 ===")

if __name__ == "__main__":
    main()