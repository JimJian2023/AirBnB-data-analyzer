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

def analyze_listing(url, driver):
    """分析单个房源"""
    logger = get_logger()
    logger.info(f"\n开始分析房源: {url}")
    
    try:
        # 1. 获取日历数据
        calendar_data, excel_file, driver = check_calendar_availability(url, driver)
        if not calendar_data:
            logger.error(f"获取日历数据失败: {url}")
            return None
            
        logger.info(f"成功获取日历数据: {len(calendar_data)} 条记录")
        
        # 2. 获取价格数据
        price_info = check_room_price(url, calendar_data, driver)
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

if __name__ == "__main__":
    # 测试URL列表
    test_urls = [
        'https://www.airbnb.co.nz/rooms/830193102361409290',
        # 添加更多URL...
    ]
    
    # 执行分析
    results = analyze_multiple_listings(test_urls)
    
    # 输出结果
    if results:
        print("\n=== 分析结果 ===")
        for result in results:
            print(f"\nURL: {result['url']}")
            print(f"数据文件: {result['calendar_excel']}")
            if result['price_info']:
                print("价格信息:")
                # 输出价格统计
                prices = [float(re.search(r'\$(\d+)', p['nightly_price']).group(1)) 
                         for p in result['price_info'] if p['nightly_price']]
                if prices:
                    print(f"  平均每晚价格: ${sum(prices)/len(prices):.2f}")
                    print(f"  最高每晚价格: ${max(prices):.2f}")
                    print(f"  最低每晚价格: ${min(prices):.2f}")
                    print(f"  价格样本数: {len(prices)}")