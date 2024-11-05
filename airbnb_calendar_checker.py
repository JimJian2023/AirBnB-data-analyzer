import time
import logging
import os
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
from logger_config import get_logger

__all__ = ['check_calendar_availability', 'export_to_excel']

def export_to_excel(calendar_data, url):
    """导出数据到Excel文件"""
    logger = get_logger()
    logger.info("开始导出数据到Excel...")
    
    try:
        # 创建data目录（如果不存在）
        if not os.path.exists('data'):
            os.makedirs('data')
            logger.info("创建data目录成功")
        
        # 从URL中提取房源ID
        room_id = url.split('rooms/')[-1].split('?')[0]
        logger.info(f"处理房源ID: {room_id}")
        
        # 创建文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'data/airbnb_calendar_{room_id}_{timestamp}.xlsx'
        logger.info(f"将创建文件: {filename}")
        
        # 创建DataFrame
        df = pd.DataFrame(calendar_data)
        logger.info(f"创建DataFrame，共 {len(df)} 行数据")
        
        # 重新排序列
        columns_order = ['date', 'status', 'is_blocked', 'cell_class', 'div_class', 'aria_label']
        df = df.reindex(columns=columns_order)
        
        # 重命名列
        df.columns = ['日期', '状态', '是否被阻止', '单元格类名', 'div类名', '描述']
        
        # 导出到Excel
        df.to_excel(filename, index=False, engine='openpyxl')
        logger.info(f"数据已成功导出到Excel文件: {filename}")
        
        # 验证文件是否创建成功
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            logger.info(f"文件创建成功，大小: {file_size/1024:.2f} KB")
        else:
            logger.warning("文件似乎未能成功创建")
        
        return filename
        
    except Exception as e:
        logger.error(f"导出数据到Excel时发生错误: {str(e)}")
        raise

def check_calendar_availability(url, driver):
    """检查房源日历可用性"""
    logger = get_logger()
    logger.info(f"开始检查房源日历: {url}")
    
    try:
        # 1. 访问页面
        driver.get(url)
        logger.info("页面加载中...")
        
        # 等待页面基本元素加载
        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            logger.info("页面基本加载完成")
        except Exception as e:
            logger.error(f"页面加载超时: {str(e)}")
        
        # 2. 尝试关闭可能的模态框
        try:
            close_buttons = driver.find_elements(By.CSS_SELECTOR, "button[aria-label='关闭']")
            if close_buttons:
                driver.execute_script("arguments[0].click();", close_buttons[0])
                logger.info("成功关闭模态框")
        except:
            logger.info("没有找到需要关闭的模态框或关闭失败")
        
        # 3. 等待并定位日历按钮
        calendar_selectors = [
            ("CSS", "button[data-testid='calendar-button']"),
            ("CSS", "button[data-testid='homes-pdp-calendar-button']"),
            ("CSS", "button[data-testid='homes-pdp-calendar-availability-button']"),
            ("CSS", "button[data-testid='pdp-availability-calendar-button']"),
            ("XPATH", "//button[contains(@data-testid, 'calendar')]"),
            ("XPATH", "//button[contains(@aria-label, 'Choose')]"),
            ("XPATH", "//button[contains(@aria-label, 'calendar')]"),
            ("XPATH", "//button[contains(@aria-label, 'availability')]")
        ]
        
        calendar_button = None
        for selector_type, selector in calendar_selectors:
            try:
                logger.debug(f"尝试选择器: {selector_type} - {selector}")
                if selector_type == "XPATH":
                    calendar_button = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                else:
                    calendar_button = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                if calendar_button:
                    logger.info(f"找到日历按钮: {selector}")
                    break
            except Exception as e:
                logger.debug(f"选择器失败 {selector}: {str(e)}")
                continue
        
        if not calendar_button:
            logger.error("未找到日历按钮")
            return None, None, driver
            
        # 4. 确保按钮可见和可点击
        try:
            # 滚动到按钮位置
            driver.execute_script("arguments[0].scrollIntoView(true);", calendar_button)
            logger.info("已滚动到日历按钮位置")
            time.sleep(1)
            
            # 直接使用原始选择器重新获取按钮
            if calendar_button:
                logger.info("日历按钮已准备就绪")
                
        except Exception as e:
            logger.error(f"准备点击按钮时出错: {str(e)}")
            return None, None, driver
            
        # 5. 点击日历按钮
        try:
            calendar_button.click()
            logger.info("直接点击日历按钮成功")
        except Exception as e1:
            logger.debug(f"直接点击失败: {str(e1)}")
            try:
                driver.execute_script("arguments[0].click();", calendar_button)
                logger.info("JavaScript点击日历按钮成功")
            except Exception as e2:
                logger.debug(f"JavaScript点击失败: {str(e2)}")
                try:
                    ActionChains(driver).move_to_element(calendar_button).click().perform()
                    logger.info("ActionChains点击日历按钮成功")
                except Exception as e3:
                    logger.error(f"所有点击方式都失败: {str(e3)}")
                    return None, None, driver
                    
        # 6. 等待日历内容加载
        calendar_content_selectors = [
            "div[data-testid='calendar-container']",
            "div[data-testid='availability-calendar']",
            "//div[contains(@data-testid, 'calendar')]",
            "//div[contains(@class, '_calendar')]//table"
        ]
        
        calendar_content = None
        for selector in calendar_content_selectors:
            try:
                logger.debug(f"尝试等待日历内容: {selector}")
                if selector.startswith("//"):
                    calendar_content = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, selector))
                    )
                else:
                    calendar_content = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                if calendar_content:
                    logger.info(f"日历内容已加载: {selector}")
                    break
            except Exception as e:
                logger.debug(f"等待日历内容失败 {selector}: {str(e)}")
                continue
                
        if not calendar_content:
            logger.error("未能加载日历内容")
            return None, None, driver
            
        # 7. 等待日历单元格加载
        try:
            date_cells = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "td[role='button']"))
            )
            logger.info(f"找到 {len(date_cells)} 个日期单元格")
        except Exception as e:
            logger.error(f"等待日期单元格加载失败: {str(e)}")
            return None, None, driver
            
        # 解析日历数据
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        calendar_data = []
        processed_dates = set()  # 用于跟踪已处理的日期
        
        # 获取所有日期单元格
        date_cells = soup.find_all('td', attrs={'role': 'button'})
        logger.info(f"找到 {len(date_cells)} 个日期单元格")
        
        for cell in date_cells:
            # 获取日期信息
            date_div = cell.find('div', {'data-testid': lambda x: x and x.startswith('calendar-day-')})
            if not date_div:
                continue
                
            # 解析日期信息
            date_str = date_div.get('data-testid', '').replace('calendar-day-', '')
            
            # 检查是否已处理过这个日期
            if date_str in processed_dates:
                logger.debug(f"跳过重复日期: {date_str}")
                continue
                
            processed_dates.add(date_str)  # 添加到已处理集合
            
            is_blocked = date_div.get('data-is-day-blocked') == 'true'
            cell_class = cell.get('class', [])[0] if cell.get('class') else ''
            aria_label = cell.get('aria-label', '')
            
            # 确定可用性状态
            availability_status = "不可预订"
            if not is_blocked and cell.get('aria-disabled') != 'true':
                if "Available" in aria_label:
                    if "only available for checkout" in aria_label:
                        availability_status = "仅可退房"
                    elif "no eligible checkout date" in aria_label:
                        availability_status = "无法选择退房日期"
                    else:
                        availability_status = "可预订"
            
            # 收集日期信息
            date_info = {
                'date': date_str,
                'status': availability_status,
                'cell_class': cell_class,
                'div_class': date_div.get('class', []),
                'aria_label': aria_label,
                'is_blocked': is_blocked
            }
            calendar_data.append(date_info)
            
        # 验证数据
        logger.info(f"原始单元格数量: {len(date_cells)}")
        logger.info(f"去重后数据条数: {len(calendar_data)}")
        logger.info(f"处理的唯一日期数: {len(processed_dates)}")
        
        # 在返回之前导出数据到Excel（只导出一次）
        if calendar_data:
            logger.info(f"收集到 {len(calendar_data)} 条有效日历数据")
            try:
                excel_file = export_to_excel(calendar_data, url)
                logger.info(f"日历数据已成功导出到: {excel_file}")
            except Exception as e:
                logger.error(f"导出Excel失败: {str(e)}")
        
        # 返回数据、Excel文件路径和driver
        return calendar_data, excel_file, driver
        
    except Exception as e:
        logger.error(f"检查日历时发生错误: {str(e)}")
        return None, None, driver


