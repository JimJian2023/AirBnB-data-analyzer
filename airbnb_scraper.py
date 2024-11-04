# 导入所需的库
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib as plt
import json
import re
import os
import logging
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from tabulate import tabulate
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from urllib.parse import urlparse, parse_qs
from retrying import retry
from webdriver_manager.chrome import ChromeDriverManager

# 设置日志函数
def setup_logger(listing_id):
    if isinstance(listing_id, str) and 'rooms/' in listing_id:
        listing_id = listing_id.split('rooms/')[-1].split('?')[0]
    
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    log_filename = f'logs/airbnb_scraper_{listing_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger()

# 日期选择函数
def select_dates(driver, checkin_date, checkout_date):
    logger.info(f"尝试选择日期: 入住 {checkin_date}, 退房 {checkout_date}")
    
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "_1ncwt1cd"))
        )
        
        checkin_xpath = f"//td[@role='button'][@aria-label[contains(., '{checkin_date}')]]"
        checkin_element = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, checkin_xpath))
        )
        logger.info("找到入住日期元素")
        checkin_element.click()
        logger.info("已点击入住日期")
        
        time.sleep(1)
        
        checkout_xpath = f"//td[@role='button'][@aria-label[contains(., '{checkout_date}')]]"
        checkout_element = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, checkout_xpath))
        )
        logger.info("找到退房日期元素")
        checkout_element.click()
        logger.info("已点击退房日期")
        
        return True
        
    except Exception as e:
        logger.error(f"选择日期失败: {str(e)}")
        return False

# 主要的爬虫函数
@retry(stop_max_attempt_number=3, wait_fixed=2000)
def scrape_listing_pricing(listing_url, guests, num_days):
    # 函数内容与原来相同
    # ... (这里是原来的函数内容)
    
 # 设置日志
    logger = setup_logger(listing_url)
    logger.info(f"开始抓取房源: {listing_url}")
    logger.info(f"设置: guests={guests}, num_days={num_days}")

    df = pd.DataFrame(columns=[
        'Check-in Date', 'Check-out Date', 'Host', 
        'Guest', 'bedrooms', 'beds', 'baths', 'years_hosting',
        'nightly_price', 'cleaning_fee', 'service_fee', 'total',
        'availability'
    ])
    
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("Chrome WebDriver 初始化成功")

        current_date = datetime.now()
        end_date = current_date + timedelta(days=num_days)
        
        # 首先访问页面获取房屋基本信息
        url = f"{listing_url}"
        logger.info(f"访问页面: {url}")
        driver.get(url)
        time.sleep(5)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        logger.info("页面解析完成")
        
        # 获取房屋基本信息
        try:
            house_elements = soup.findAll(class_='l7n4lsf atm_9s_1o8liyq_keqd55 dir dir-ltr')
            logger.info(f"找到 {len(house_elements)} 个房屋信息元素")

            if house_elements and len(house_elements) >= 5:
                def safe_extract_number(text):
                    match = re.search(r'\d+', text)
                    return float(match.group()) if match else 'NaN'
                
                Guests = safe_extract_number(house_elements[0].text)
                bedrooms = safe_extract_number(house_elements[1].text)
                beds = safe_extract_number(house_elements[2].text)
                baths = safe_extract_number(house_elements[3].text)
                years_hosting = safe_extract_number(house_elements[4].text)

                logger.info(f"房屋信息: Guests={Guests}, bedrooms={bedrooms}, beds={beds}, "
                          f"baths={baths}, years_hosting={years_hosting}")
            else:
                logger.warning("未找到足够的房屋信息元素")
                Guests = bedrooms = beds = baths = years_hosting = 'NaN'
        except Exception as e:
            logger.error(f"获取房屋信息出错: {str(e)}")
            Guests = bedrooms = beds = baths = years_hosting = 'NaN'

        success_count = 0
        fail_count = 0
        
        while current_date <= end_date:
            try:
                checkin_date = current_date.strftime('%Y-%m-%d')
                checkout_date = (current_date + timedelta(days=2)).strftime('%Y-%m-%d')

                logger.info(f"\n处理日期: {checkin_date} 到 {checkout_date}")
                
                url = f"{listing_url}?check_in={checkin_date}&guests={guests}&adults={guests}&check_out={checkout_date}"
                driver.get(url)
                time.sleep(3)
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # 检查日期可用性
                date_cells = soup.find_all('td', attrs={'role': 'button'})
                logger.info(f"找到 {len(date_cells)} 个日期单元格")
                is_available = True  # 默认可用
                
                for cell in date_cells:
                    date_label = cell.get('aria-label', '')
                    if checkin_date in date_label:
                        is_available = cell.get('aria-disabled') != 'true'
                        logger.info(f"日期 {checkin_date} 可用性: {'可用' if is_available else '不可用'}")

                        break
                
                # 如果日期不可用，添加基本信息并跳过价格抓取
                if not is_available:
                    logger.info(f"日期 {checkin_date} 不可预订，跳过价格抓取")
                    df = pd.concat([df, pd.DataFrame({
                        'Host': [listing_url],
                        'Check-in Date': [checkin_date],
                        'Check-out Date': [checkout_date],
                        'Guest': [Guests],
                        'bedrooms': [bedrooms],
                        'beds': [beds],
                        'baths': [baths],
                        'years_hosting': [years_hosting],
                        'nightly_price': ['NaN'],
                        'cleaning_fee': ['NaN'],
                        'service_fee': ['NaN'],
                        'total': ['NaN'],
                        'availability': ['Unavailable']
                    })], ignore_index=True)
                    print(f"{checkin_date} 不可预订，跳过价格抓取")
                    current_date += timedelta(days=1)
                    continue
                
                # 日期可用时抓取价格信息
                try:
                    scripts = soup.find_all('script', {'type': 'application/json'})
                    logger.info(f"找到 {len(scripts)} 个JSON脚本")

                    pricing_data = {
                        "nightly_price": 'NaN',
                        "cleaning_fee": 'NaN',
                        "service_fee": 'NaN',
                        "total": 'NaN'
                    }
                    
                    price_found = False
                    for script in scripts:
                        try:
                            data = json.loads(script.string)
                            if 'pdp_listing_booking_details' in str(data):
                                pricing_module = data.get('pdp_listing_booking_details', {})
                                pricing_data["nightly_price"] = pricing_module.get('price', {}).get('rate', {}).get('amount', 'NaN')
                                pricing_data["cleaning_fee"] = pricing_module.get('price', {}).get('cleaning_fee', {}).get('amount', 'NaN')
                                pricing_data["service_fee"] = pricing_module.get('price', {}).get('service_fee', {}).get('amount', 'NaN')
                                pricing_data["total"] = pricing_module.get('price', {}).get('total', {}).get('amount', 'NaN')
                                logger.info(f"价格信息: {pricing_data}")
                                break
                        except json.JSONDecodeError:
                            continue
                    if not price_found:
                        logger.warning("未找到价格信息")
                except Exception as e:
                    logger.error(f"提取定价数据时出错: {str(e)}")
                
                # 添加可用日期的完整数据
                df = pd.concat([df, pd.DataFrame({
                    'Host': [listing_url],
                    'Check-in Date': [checkin_date],
                    'Check-out Date': [checkout_date],
                    'Guest': [Guests],
                    'bedrooms': [bedrooms],
                    'beds': [beds],
                    'baths': [baths],
                    'years_hosting': [years_hosting],
                    'nightly_price': [pricing_data["nightly_price"]],
                    'cleaning_fee': [pricing_data["cleaning_fee"]],
                    'service_fee': [pricing_data["service_fee"]],
                    'total': [pricing_data["total"]],
                    'availability': ['Available']
                })], ignore_index=True)

                success_count += 1
                logger.info(f"成功抓取日期 {checkin_date} 的数据")
                
            except Exception as e:
                fail_count += 1
                logger.error(f"处理日期 {checkin_date} 时出错: {str(e)}")
                
            finally:
                current_date += timedelta(days=1)

        logger.info(f"\n抓取统计:")
        logger.info(f"总天数: {num_days}")
        logger.info(f"成功天数: {success_count}")
        logger.info(f"失败天数: {fail_count}")
        logger.info(f"成功率: {(success_count/num_days)*100:.2f}%")
                
    except Exception as e:
        logger.error(f"抓取过程出错: {str(e)}")
        
    finally:
        driver.quit()
        logger.info("浏览器已关闭")
        
    return df

# 主程序
if __name__ == "__main__":
    # 读取URL列表
    urls = [
        'https://www.airbnb.co.nz/rooms/837352260137971048',
        # ... 其他URL
    ]
    
    # 创建DataFrame并保存到Excel
    df = pd.DataFrame(urls, columns=['URL'])
    df.to_excel('urls.xlsx', index=False)
    
    # 读取Excel文件并处理每个URL
   # df = pd.read_excel('urls.xlsx')
   # guests = 3
   # num_days = 10
   # 
   # for listing_url in df['URL']:
   #     print(listing_url)
   #     pricing_data = scrape_listing_pricing(listing_url, guests, num_days)
    
    # 保存结果
    #pricing_data.to_excel('pricing_data.xlsx', index=False) 