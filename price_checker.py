import time
import os
from datetime import datetime, timedelta
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from airbnb_calendar_checker import check_calendar_availability
from logger_config import get_logger
import re
from selenium.common.exceptions import TimeoutException

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

def find_first_available_date(calendar_data):
    """查找第一个可预订的日期"""
    logger = get_logger()
    
    for date_info in calendar_data:
        if date_info['status'] == "可预订":
            logger.info(f"找到第一个可预订日期: {date_info['date']}")
            return date_info['date']
    
    logger.warning("未找到可预订日期")
    return None

def calculate_checkout_date(checkin_date_str, min_nights):
    """根据最小入住天数计算退房日期"""
    checkin_date = datetime.strptime(checkin_date_str, '%d/%m/%Y')
    checkout_date = checkin_date + timedelta(days=min_nights)
    return checkout_date.strftime('%d/%m/%Y')

def check_booking_availability(driver, checkin_date, checkout_date):
    """检查指定日期区间是否可预订"""
    logger = get_logger()
    try:
        # 等待预订按钮出现
        book_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button[data-testid='homes-pdp-cta-btn']"))
        )
        
        # 检查按钮是否可点击
        if book_button.is_enabled():
            logger.info(f"日期区间 {checkin_date} 到 {checkout_date} 可预订")
            return True
        else:
            logger.warning(f"日期区间 {checkin_date} 到 {checkout_date} 不可预订")
            return False
            
    except Exception as e:
        logger.error(f"检查预订可用性时出错: {str(e)}")
        return False

def get_price_info(driver, url, checkin_date, min_nights):
    """获取价格信息"""
    logger = get_logger()
    logger.info(f"开始获取价格信息: {url}")
    
    try:
        # 计算退房日期时使用最小入住天数
        checkin_dt = datetime.strptime(checkin_date, '%d/%m/%Y')
        checkout_dt = checkin_dt + timedelta(days=min_nights)
        
        # 使用正确的日期格式
        checkin_str = checkin_dt.strftime('%Y-%m-%d')
        checkout_str = checkout_dt.strftime('%Y-%m-%d')
        
        logger.info(f"入住日期: {checkin_str}, 退房日期: {checkout_str} (最小入住: {min_nights}晚)")
        
        # 3. 访问带日期参数的URL
        url_with_dates = f"{url}?check_in={checkin_str}&check_out={checkout_str}&adults=3&children=0&infants=0"
        logger.info(f"访问URL: {url_with_dates}")
        driver.get(url_with_dates)
        time.sleep(10)  # 增加页面加载等待时间
        
        # 添加页面状态检查
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            if check_page_state(driver):
                break
            retry_count += 1
            time.sleep(5)
            logger.info(f"等待页面就绪，重试 {retry_count}/{max_retries}")
            
        if retry_count == max_retries:
            logger.error("页面状态检查失败，超过最大重试次数")
            return None
            
        # 添加显式等待，确保页面完全加载
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # 等待价格容器出现前，先确认页面是否完全加载
        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            logger.info("页面加载完成")
        except TimeoutException:
            logger.warning("页面加载超时")
        
        # 4. 验证日期区间是否可预订
        if not check_booking_availability(driver, checkin_date, checkout_str):
            logger.error("所选日期区间不可预订")
            return None
            
        # 5. 获取价格信息
        try:
            # 使用多个备选选择器尝试定位价格详情按钮
            show_details_selectors = [
                "button[aria-label='Show price details']",
                "button._12wl7g09",  # 使用类名
                "//button[contains(text(), 'Show price details')]",  # 使用XPath
                "//button[.//span[contains(text(), 'Show price details')]]"  # 更复杂的XPath
            ]
            
            show_details_button = None
            for selector in show_details_selectors:
                try:
                    if selector.startswith("//"):
                        # XPath选择器
                        show_details_button = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, selector))
                        )
                    else:
                        # CSS选择器
                        show_details_button = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                    if show_details_button:
                        logger.info(f"找到价格详情按钮，使用选择器: {selector}")
                        break
                except Exception:
                    continue
            
            if not show_details_button:
                logger.error("未找到价格详情按钮")
                return None
                
            # 尝试多种点击方式
            try:
                # 方式1：直接点击
                show_details_button.click()
            except Exception:
                try:
                    # 方式2：JavaScript点击
                    driver.execute_script("arguments[0].click();", show_details_button)
                except Exception:
                    try:
                        # 方式3：Actions链点击
                        ActionChains(driver).move_to_element(show_details_button).click().perform()
                    except Exception as e:
                        logger.error(f"所有点击方式都失败: {str(e)}")
                        return None
                        
            logger.info("成功点击展开价格详情按钮")
            time.sleep(3)  # 等待展开动画完成
            
            # 验证价格详情是否成功展开
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div._14omvfj"))
                )
                logger.info("价格详情已成功展开")
            except Exception:
                logger.error("价格详情未成功展开")
                return None
                
            # 初始化价格信息
            price_info = {
                'check_in': checkin_date,
                'check_out': checkout_str,
                'guests': 3,
                'nightly_price': None,
                'cleaning_fee': None,
                'service_fee': None,
                'taxes': None,
                'total': None
            }
            
            # 获取每晚价格
            try:
                nightly_price = driver.find_element(By.CSS_SELECTOR, "span._11jcbg2").text
                price_info['nightly_price'] = nightly_price
                logger.info(f"获取到每晚价格: {nightly_price}")
            except Exception as e:
                logger.warning(f"获取每晚价格失败: {str(e)}")

            # 获取详细价格项
            try:
                price_items = driver.find_elements(By.CSS_SELECTOR, "div._14omvfj")
                for item in price_items:
                    try:
                        label = item.find_element(By.CSS_SELECTOR, "div.l1x1206l").text.strip()
                        value = item.find_element(By.CSS_SELECTOR, "span._1k4xcdh").text.strip()
                        
                        if "x" in label.lower() and "night" in label.lower():
                            price_info['nightly_price'] = value
                        elif "cleaning fee" in label.lower():
                            price_info['cleaning_fee'] = value
                        elif "service fee" in label.lower():
                            price_info['service_fee'] = value
                        elif "taxes" in label.lower():
                            price_info['taxes'] = value
                        
                        logger.info(f"获取到价格项: {label} = {value}")
                    except Exception as e:
                        logger.warning(f"处理价格项时出错: {str(e)}")
                        continue
            except Exception as e:
                logger.error(f"获取价格详情失败: {str(e)}")

            # 修改获取总价的部分
            try:
                total_elem = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div._1avmy66 span._j1kt73"))
                )
                total_price = total_elem.text.strip()
                if "$" in total_price and "NZD" in total_price:
                    logger.info(f"获取到总价: {total_price}")
                    price_info['total'] = total_price
                else:
                    logger.error("获取到的总价格式不正确")
                    return None
            except Exception as e:
                logger.error(f"获取总价失败: {str(e)}")
                return None

            # 验证是否获取到了所有必要的价格信息
            if price_info['nightly_price'] and price_info['total']:
                logger.info(f"成功获取价格信息: {price_info}")
                return price_info
            else:
                logger.error("部分关键价格信息缺失")
                return None
                
        except Exception as e:
            logger.error(f"获取价格容器失败: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"获取价格信息时发生错误: {str(e)}")
        return None

def export_price_data(price_data, url):
    """导出价格数据到Excel"""
    logger = get_logger()
    
    try:
        # 创建data目录（如果不存在）
        if not os.path.exists('data'):
            os.makedirs('data')
        
        # 从URL中提取房源ID
        room_id = url.split('rooms/')[-1].split('?')[0]
        
        # 创建文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'data/airbnb_price_{room_id}_{timestamp}.xlsx'
        
        # 创建DataFrame
        if isinstance(price_data, list):
            df = pd.DataFrame(price_data)
        else:
            df = pd.DataFrame([price_data])
        
        # 保存到Excel
        df.to_excel(filename, index=False)
        logger.info(f"价格数据已保存到: {filename}")
        
        # 输出统计信息
        if isinstance(price_data, list):
            logger.info(f"共导出 {len(price_data)} 条价格记录")
            
            # 计算平均价格等统计信息
            try:
                nightly_prices = [float(re.search(r'\$(\d+)', p['nightly_price']).group(1)) 
                                for p in price_data if p['nightly_price']]
                if nightly_prices:
                    avg_price = sum(nightly_prices) / len(nightly_prices)
                    max_price = max(nightly_prices)
                    min_price = min(nightly_prices)
                    logger.info(f"价格统计: 平均={avg_price:.2f}, 最高={max_price}, 最低={min_price}")
            except Exception as e:
                logger.warning(f"计算价格统计信息时出错: {str(e)}")
        
        return filename
        
    except Exception as e:
        logger.error(f"导出价格数据时发生错误: {str(e)}")
        return None

def find_all_available_dates(calendar_data):
    """查找所有可预订的日期"""
    logger = get_logger()
    available_dates = []
    
    for date_info in calendar_data:
        if date_info['status'] == "可预订":
            available_dates.append(date_info['date'])
    
    logger.info(f"找到 {len(available_dates)} 个可预订日期")
    return available_dates

def check_room_price(url_info, calendar_data, driver):
    """检查房间价格"""
    logger = get_logger()
    url = url_info['url']
    min_nights = url_info['min_nights']
    logger.info(f"开始检查房源价格: {url} (最小入住: {min_nights}晚)")
    
    try:
        # 查找所有可预订日期
        available_dates = find_all_available_dates(calendar_data)
        if not available_dates:
            logger.error(f"房源 {url} 未找到可预订日期")
            return None
            
        # 存储所有日期的价格信息
        all_price_info = []
        failed_dates = []
        
        # 遍历每个可预订日期
        for index, check_in_date in enumerate(available_dates, 1):
            try:
                logger.info(f"[{index}/{len(available_dates)}] 处理日期: {check_in_date}")
                
                # 获取该日期的价格信息
                price_info = get_price_info(driver, url, check_in_date, min_nights)
                if price_info:
                    all_price_info.append(price_info)
                    logger.info(f"✓ 成功获取 {check_in_date} 的价格信息")
                else:
                    failed_dates.append(check_in_date)
                    logger.warning(f"✗ 获取 {check_in_date} 的价格信息失败")
                
                # 每处理5个日期暂停一下
                if index % 5 == 0:
                    logger.info(f"已完成 {index}/{len(available_dates)} 个日期的处理")
                    time.sleep(10)
                    
            except Exception as e:
                failed_dates.append(check_in_date)
                logger.error(f"处理日期 {check_in_date} 时发生错误: {str(e)}")
                continue
        
        # 统计处理结果
        logger.info("\n=== 价格数据收集统计 ===")
        logger.info(f"总可预订日期: {len(available_dates)}")
        logger.info(f"成功收集: {len(all_price_info)}")
        logger.info(f"失败日期: {len(failed_dates)}")
        
        if failed_dates:
            logger.warning("失败日期列表:")
            for date in failed_dates:
                logger.warning(f"- {date}")
        
        # 导出数据
        if all_price_info:
            excel_file = export_price_data(all_price_info, url)
            if excel_file:
                logger.info(f"✓ 所有价格数据已导出到: {excel_file}")
                return all_price_info
            else:
                logger.error("导出价格数据失败")
                return None
        else:
            logger.error("未能获取任何价格信息")
            return None
            
    except Exception as e:
        logger.error(f"检查房间价格时发生错误: {str(e)}")
        return None

def get_price_container(driver):
    """使用多个备选选择器尝试获取价格容器"""
    logger = get_logger()
    selectors = [
        "div._wgmchy div._1k1ce2w ._11jcbg2",  # 原始选择器
        "div[data-testid='book-it-default']",   # 使用data-testid
        "div._wgmchy",                          # 简化选择器
        "span._1qgfaxb1"                        # 备选选择器
    ]
    
    for selector in selectors:
        try:
            logger.info(f"尝试使用选择器: {selector}")
            container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            if container:
                logger.info(f"成功找到价格容器，使用选择器: {selector}")
                return container
        except Exception as e:
            logger.warning(f"选择器 {selector} 失败: {str(e)}")
            continue
    
    logger.error("所有选择器都失败")
    return None

def parse_price(self, container):
    try:
        # 获取每晚价格
        price_element = container.find_element(By.CLASS_NAME, "_11jcbg2")
        price_text = price_element.text  # 例如 "$165 NZD"
        
        # 提取数字
        price = float(re.search(r'\$(\d+)', price_text).group(1))
        return price
    except Exception as e:
        logging.error(f"解析价格失败: {str(e)}")
        return None

def check_page_state(driver):
    """检查页面状态和可能的错误"""
    logger = get_logger()
    try:
        # 检查是否有错误消息
        error_messages = driver.find_elements(By.CSS_SELECTOR, "[data-testid*='error']")
        if error_messages:
            logger.error(f"页面显示错误: {error_messages[0].text}")
            return False
            
        # 检查是否有加载指示器
        loading_indicators = driver.find_elements(By.CSS_SELECTOR, "[role='progressbar']")
        if loading_indicators:
            logger.warning("页面仍在加载中")
            return False
            
        # 检查价格区域是否可见
        price_area = driver.find_elements(By.CSS_SELECTOR, "div._wgmchy")
        if not price_area:
            logger.error("价格区域不可见")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"检查页面状态时出错: {str(e)}")
        return False