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
import traceback
from data_export import exporter

# 更新价格选择器配置
PRICE_SELECTORS = [
    # 1. 使用更精确的价格选择器
    ("xpath", "//div[@data-testid='book-it-default']//span[contains(@class, '_1y74zjx')]"),
    ("xpath", "//div[@data-testid='book-it-default']//span[contains(@class, '_tyxjp1')]"),
    
    # 2. 使用价格的父容器结构
    ("css", "div._wgmchy div._1k1ce2w span._1qgfaxb1"),
    ("css", "div._wgmchy div._1k1ce2w ._11jcbg2"),
    
    # 3. 使用更通用的价格特征
    ("xpath", "//div[contains(@class, '_wgmchy')]//span[contains(text(), '$') and contains(text(), 'NZD')]"),
]

SHOW_DETAILS_SELECTORS = [
    # 1. 使用文本内容和class组合
    ("xpath", "//button[contains(@class, '_12wl7g09')]//div[contains(text(), 'x 1 night')]"),
    ("xpath", "//button[contains(@class, '_12wl7g09')]//div[contains(text(), 'Cleaning fee')]"),
    ("xpath", "//button[contains(@class, '_12wl7g09')]//div[contains(text(), 'service fee')]"),
    ("xpath", "//button[contains(@class, '_12wl7g09')]//div[contains(text(), 'Taxes')]"),
    
    # 2. 使用父子关系
    ("xpath", "//div[contains(@class, '_14omvfj')]//button[contains(@class, '_12wl7g09')]"),
    
    # 3. 使用更精确的定位
    ("xpath", "//div[contains(@class, '_10d7v0r')]/button[contains(@class, '_12wl7g09')]"),
]

# 更新价格详情选择器配置
PRICE_DETAIL_SELECTORS = [
    # 清洁费 - 多种匹配方式
    ("xpath", "//div[contains(@class, '_14omvfj')][.//div[text()='Cleaning fee']]//span[contains(@class, '_1k4xcdh')]"),
    ("xpath", "//div[contains(@class, '_14omvfj')][.//div[contains(text(), 'Cleaning fee')]]//span[contains(@class, '_1k4xcdh')]"),
    
    # 服务费 - 多种匹配方式
    ("xpath", "//div[contains(@class, '_14omvfj')][.//div[text()='Airbnb service fee']]//span[contains(@class, '_1k4xcdh')]"),
    ("xpath", "//div[contains(@class, '_14omvfj')][.//div[contains(text(), 'service fee')]]//span[contains(@class, '_1k4xcdh')]"),
    
    # 税费 - 多种匹配方式
    ("xpath", "//div[contains(@class, '_14omvfj')][.//div[text()='Taxes']]//span[contains(@class, '_1k4xcdh')]"),
    ("xpath", "//div[contains(@class, '_14omvfj')][.//div[contains(text(), 'tax')]]//span[contains(@class, '_1k4xcdh')]"),
    
    # 总价 - 多种匹配方式
    ("xpath", "//div[contains(@class, '_1avmy66')]//span[contains(@class, '_j1kt73')]"),
    ("xpath", "//div[contains(@class, '_1avmy66')]//span[contains(@class, '_1qs94rc')]//span")
]

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

def find_price_element(driver, selectors_config):
    """使用多种选择器策略查找价格元素"""
    logger = get_logger()
    
    for selector_type, selector_value in selectors_config:
        try:
            if selector_type == "css":
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector_value))
                )
            elif selector_type == "xpath":
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, selector_value))
                )
            
            if element:
                logger.info(f"成功找到元素，使用{selector_type}: {selector_value}")
                return element
        except Exception as e:
            logger.debug(f"选择器 {selector_value} 失败: {str(e)}")
            continue
    
    return None

def min_nights_check(driver, date_element):
    """
    检查日期元素的最小入住天数要求
    """
    logger = get_logger()
    try:
        # 记录初始状态
        initial_html = date_element.get_attribute('outerHTML')
        logger.info(f"初始元素HTML: {initial_html}")
        
        # 获取日期信息
        try:
            date_div = date_element.find_element(By.XPATH, ".//div[contains(@data-testid, 'calendar-day-')]")
            date_str = date_div.get_attribute('data-testid').replace('calendar-day-', '')
            logger.info(f"找到日期: {date_str}")
        except Exception as e:
            logger.error(f"获取日期信息失败: {str(e)}")
            return 1
            
        # 先点击日期元素
        logger.info("点击日期元素...")
        try:
            date_element.click()
            time.sleep(1)  # 等待状态更新
        except Exception as e:
            logger.warning(f"点击日期元素失败，尝试使用JavaScript点击: {str(e)}")
            driver.execute_script("arguments[0].click();", date_element)
            time.sleep(1)
            
        # 移动到日期元素上
        logger.info("移动到日期元素...")
        actions = ActionChains(driver)
        actions.move_to_element(date_element).perform()
        time.sleep(1)
        
        # 重新获取更新后的元素
        try:
            # 使用多个class名称尝试定位
            selectors = [
                f"//td[.//div[@data-testid='calendar-day-{date_str}']]",
                "//td[contains(@class, '_5v1jabe')]",  # 选中状态的class
                "//td[contains(@class, '_1fmu67uy')]"  # 未选中状态的class
            ]
            
            updated_element = None
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            updated_element = elem
                            break
                    if updated_element:
                        break
                except:
                    continue
                    
            if not updated_element:
                updated_element = date_element  # 如果找不到，使用原始元素
                
        except Exception as e:
            logger.warning(f"重新获取元素失败: {str(e)}")
            updated_element = date_element
            
        # 记录更新后的状态
        updated_html = updated_element.get_attribute('outerHTML')
        logger.info(f"更新后元素HTML: {updated_html}")
        
        # 获取并记录所有相关属性
        aria_label = updated_element.get_attribute('aria-label')
        aria_disabled = updated_element.get_attribute('aria-disabled')
        is_blocked = updated_element.get_attribute('data-is-day-blocked')
        
        logger.info(f"更新后元素属性:")
        logger.info(f"- aria-label: {aria_label}")
        logger.info(f"- aria-disabled: {aria_disabled}")
        logger.info(f"- data-is-day-blocked: {is_blocked}")
        
        # 使用正则表达式查找最小入住要求
        if aria_label:
            patterns = [
                r'(\d+)\s*night minimum stay',
                r'minimum stay[:\s]+(\d+)',
                r'至少住(\d+)晚',
                r'最少(\d+)晚'
            ]
            
            for pattern in patterns:
                min_stay_match = re.search(pattern, aria_label, re.IGNORECASE)
                if min_stay_match:
                    min_nights = int(min_stay_match.group(1))
                    logger.info(f"✓ 成功找到最小入住要求: {min_nights}晚 (匹配模式: {pattern})")
                    return min_nights
                    
            logger.info("未在aria-label中找到最小入住要求")
        
        # 如果所有方法都失败，使用默认值
        logger.warning("⚠ 未找到最小入住要求，使用默认值1晚")
        return 1
        
    except Exception as e:
        logger.error(f"检查最小入住天数时出错: {str(e)}")
        logger.error(f"错误类型: {type(e).__name__}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        logger.warning("使用默认值1晚")
        return 1

def get_price_info(driver, url, checkin_date, min_nights=None):
    """获取价格信息"""
    logger = get_logger()
    logger.info(f"开始获取价格信息: {url}")
    logger.info(f"入住日期: {checkin_date}")
    
    try:
        # 先访问页面
        driver.get(url)
        time.sleep(5)
        
        # 找到日期单元格
        date_str = datetime.strptime(checkin_date, '%d/%m/%Y').strftime('%d/%m/%Y')
        date_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//div[@data-testid='calendar-day-{date_str}']/..")
            )
        )
        
        # 检查最小入住要求
        logger.info(f"开始检查日期 {checkin_date} 的最小入住要求...")
        actual_min_nights = min_nights_check(driver, date_element) if min_nights is None else min_nights
        logger.info(f"最终使用的最小入住天数: {actual_min_nights}晚 ({'自动检测' if min_nights is None else '手动指定'})")
        
        # 计算退房日期
        checkin_dt = datetime.strptime(checkin_date, '%d/%m/%Y')
        checkout_dt = checkin_dt + timedelta(days=actual_min_nights)
        
        # 初始化价格信息字典
        price_info = {
            'check_in': checkin_date,
            'check_out': checkout_dt.strftime('%d/%m/%Y'),
            'min_nights': actual_min_nights,
            'guests': 3,
            'nightly_price': None,
            'cleaning_fee': None,
            'service_fee': None,
            'taxes': None,
            'total': None
        }
        
        # 构建带日期参数的URL
        checkin_str = checkin_dt.strftime('%Y-%m-%d')
        checkout_str = checkout_dt.strftime('%Y-%m-%d')
        url_with_dates = f"{url}?check_in={checkin_str}&check_out={checkout_str}&adults=3&children=0&infants=0"
        logger.info(f"访问URL: {url_with_dates}")
        
        # 访问页面
        driver.get(url_with_dates)
        time.sleep(5)  # 等待页面加载
        
        # 记录页面状态
        logger.info("检查页面状态...")
        page_state = driver.execute_script("return document.readyState")
        logger.info(f"页面状态: {page_state}")
        
        # 等待价格容器加载并确保可见
        try:
            WebDriverWait(driver, 20).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            price_container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='book-it-default']"))
            )
            # 确保价格容器可见
            driver.execute_script("arguments[0].scrollIntoView(true);", price_container)
            time.sleep(2)  # 等待滚动完成
            logger.info("价格容器已加载并可见")
        except Exception as e:
            logger.error(f"等待价格容器超时: {str(e)}")
            return None
            
        # 获取每晚价格
        nightly_price_element = None
        for selector_type, selector in PRICE_SELECTORS:
            try:
                logger.info(f"尝试价格选择器: {selector_type} - {selector}")
                elements = driver.find_elements(
                    By.CSS_SELECTOR if selector_type == "css" else By.XPATH,
                    selector
                )
                logger.info(f"找到 {len(elements)} 个价格元素")
                
                for element in elements:
                    if element.is_displayed():
                        price_text = element.text.strip()
                        logger.info(f"找到可见价格元素: {price_text}")
                        if "$" in price_text and "NZD" in price_text:
                            nightly_price_element = element
                            break
                            
                if nightly_price_element:
                    break
            except Exception as e:
                logger.warning(f"使用选择器 {selector} 时出错: {str(e)}")
                continue
                
        if nightly_price_element:
            price_text = nightly_price_element.text.strip()
            logger.info(f"找到每晚价格元素: {price_text}")
            try:
                # 优先获取折扣价格
                discounted_price = re.search(r'\$(\d+)\s*NZD\s+per night', price_text)
                if discounted_price:
                    price_info['nightly_price'] = f"${discounted_price.group(1)} NZD"
                    logger.info(f"成功解析折扣价格: {price_info['nightly_price']}")
                else:
                    # 尝试获取原始价格
                    original_price = re.search(r'\$(\d+)\s*NZD', price_text)
                    if original_price:
                        price_info['nightly_price'] = f"${original_price.group(1)} NZD"
                        logger.info(f"成功解析原始价格: {price_info['nightly_price']}")
                    else:
                        logger.warning(f"价格文本格式不符合预期: {price_text}")
            except Exception as e:
                logger.error(f"解析价格文本时出错: {str(e)}")
                
        # 修改价格详情获取部分
        logger.info("开始获取价格详情...")
        price_details_found = False
        
        # 等待价格详情容器加载，缩短等待时间
        try:
            price_container = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CLASS_NAME, "_1n7cvm7"))
            )
            logger.info("价格详情容器已加载")
            
            # 确保价格容器可见
            driver.execute_script("arguments[0].scrollIntoView(true);", price_container)
            time.sleep(0.5)  # 短暂等待滚动完成
            
        except TimeoutException:
            logger.warning("等待价格详情容器超时")
        
        # 遍历所有价格详情选择器
        for selector_type, selector in PRICE_DETAIL_SELECTORS:
            try:
                logger.info(f"尝试使用选择器获取价格详情: {selector}")
                
                # 缩短等待时间到2秒
                elements = WebDriverWait(driver, 2).until(
                    EC.presence_of_all_elements_located(
                        (By.XPATH if selector_type == "xpath" else By.CSS_SELECTOR, selector)
                    )
                )
                
                logger.info(f"找到 {len(elements)} 个匹配元素")
                
                for element in elements:
                    price_text = element.get_attribute('textContent').strip()
                    element_html = element.get_attribute('outerHTML')
                    logger.info(f"找到价格元素: {price_text} (HTML: {element_html})")
                    
                    # 根据选择器内容设置价格信息
                    if "Cleaning fee" in selector or "cleaning fee" in selector.lower():
                        price_info['cleaning_fee'] = price_text
                        logger.info(f"✓ 成功设置清洁费: {price_text}")
                        price_details_found = True
                    elif "service fee" in selector.lower():
                        price_info['service_fee'] = price_text
                        logger.info(f"✓ 成功设置服务费: {price_text}")
                        price_details_found = True
                    elif "tax" in selector.lower():
                        price_info['taxes'] = price_text
                        logger.info(f"✓ 成功设置税费: {price_text}")
                        price_details_found = True
                    elif "_j1kt73" in selector or "_1qs94rc" in selector:
                        price_info['total'] = price_text
                        logger.info(f"✓ 成功设置总价: {price_text}")
                        price_details_found = True
                        
            except TimeoutException:
                continue
            except Exception as e:
                logger.warning(f"使用选择器 {selector} 获取价格详情时出错: {str(e)}")
                continue
            
        # 如果没有找到任何价格详情，尝试点击展开按钮
        if not price_details_found:
            try:
                # 尝试点击价格展开按钮
                show_price_button = driver.find_element(By.XPATH, "//button[contains(@class, '_12wl7g09')]")
                show_price_button.click()
                time.sleep(1)
                
                # 重新执行一次价格获取
                logger.info("点击展开按钮后重新获取价格详情...")
                # 递归调用，但不再尝试点击展开
                return get_price_info(driver, url, checkin_date, min_nights)
                
            except Exception as e:
                logger.warning(f"尝试点击价格展开按钮失败: {str(e)}")
        
        # 验证价格信息完整性
        logger.info("验证价格信息完整性:")
        expected_fields = ['cleaning_fee', 'service_fee', 'taxes', 'total']
        for field in expected_fields:
            if price_info.get(field):
                logger.info(f"✓ {field}: {price_info[field]}")
            else:
                logger.warning(f"✗ {field} 未获取到")
                
        # 记录最终价格信息获取结果
        logger.info("终价格信息获取结果:")
        for key, value in price_info.items():
            logger.info(f"{key}: {value}")
            
        return price_info
            
    except Exception as e:
        logger.error(f"获取价格信息时发生错误: {str(e)}")
        logger.error(f"错误详情: {str(e.__class__.__name__)}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")
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
    logger.info(f"开始检查房源价格: {url}")
    
    try:
        # 查找所有可预订日期
        available_dates = find_all_available_dates(calendar_data)
        if not available_dates:
            logger.error(f"房 {url} 未找到可预订日期")
            return None
        
        # 存储所有日期的价格信息
        all_price_info = []
        failed_dates = []
        
        # 遍历每个可预订日期
        for index, check_in_date in enumerate(available_dates, 1):
            try:
                logger.info(f"[{index}/{len(available_dates)}] 处理日期: {check_in_date}")
                
                # 获取该日期的价格信息，让函数自动检查最小入住天数
                price_info = get_price_info(driver, url, check_in_date)
                if price_info:
                    all_price_info.append(price_info)
                    logger.info(f"✓ 成功获取 {check_in_date} 的价格信息")
                    
                    # 根据最小入住天数跳过后续日期
                    min_nights = price_info['min_nights']
                    if min_nights > 1:
                        skip_count = min_nights - 1
                        logger.info(f"根据最小入住要求({min_nights}晚)跳过接下来的 {skip_count} 天")
                        index += skip_count
                else:
                    failed_dates.append(check_in_date)
                    logger.warning(f"✗ 获取 {check_in_date} 的价格信息失败")
                
                # 每处理5个日期暂停一
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
            export_result = exporter.export_price_data(all_price_info, url_info['url'])
            if not export_result:
                logger.error("价格数据导出失败")
                return None
            
            return all_price_info
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
        # 检查是否有误消息
        error_messages = driver.find_elements(By.CSS_SELECTOR, "[data-testid*='error']")
        if error_messages:
            logger.error(f"页面显示错: {error_messages[0].text}")
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