import requests
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from logger_config import get_logger
import base64
import traceback
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

class BitBrowserManager:
    def __init__(self):
        self.url = "http://127.0.0.1:54345"
        self.headers = {'Content-Type': 'application/json'}
        self.logger = get_logger()
        
        # 存储所有活动的浏览器实例
        self.active_drivers = {}  # {browser_id: driver}
        
        # 等待时间配置
        self.page_load_timeout = 30
        self.implicit_wait = 10
        self.connect_retry_delay = 1
        self.connect_max_retries = 2
        self.tab_switch_wait = 0.5

    def get_all_browsers(self):
        """获取所有活着的浏览器窗口信息"""
        try:
            response = requests.post(
                f"{self.url}/browser/pids/all",
                headers=self.headers
            )
            
            response_json = response.json()
            self.logger.info(f"活动浏览器响应: {json.dumps(response_json, indent=2)}")
            
            if response_json.get('success'):
                alive_browsers = response_json.get('data', {})
                if alive_browsers:
                    # 返回所有活着的浏览器信息
                    browser_info = []
                    for browser_id, pid in alive_browsers.items():
                        # 获取浏览器详细信息
                        detail_response = requests.post(
                            f"{self.url}/browser/detail",
                            headers=self.headers,
                            data=json.dumps({"id": browser_id})
                        ).json()
                        
                        if detail_response.get('success'):
                            browser_data = detail_response['data']
                            browser_info.append({
                                'id': browser_id,
                                'pid': pid,
                                'name': browser_data.get('name', ''),
                                'remark': browser_data.get('remark', ''),
                                'status': browser_data.get('status', 0)
                            })
                            
                    self.logger.info(f"找到 {len(browser_info)} 个活动浏览器")
                    return browser_info
                    
            self.logger.warning("未找到活动的浏览器窗口")
            return []
            
        except Exception as e:
            self.logger.error(f"获取活动浏览器失败: {str(e)}")
            return []

    def connect_browser(self, url=None, browser_id=None):
        """连接到指定的浏览器实例"""
        try:
            # 如果没有指定browser_id，获取所有浏览器让用户选择
            if not browser_id:
                browsers = self.get_all_browsers()
                if not browsers:
                    self.logger.error("没有可用的浏览器实例")
                    return None
                    
                # 如果只有一个浏览器，直接使用
                if len(browsers) == 1:
                    browser_id = browsers[0]['id']
                else:
                    # 打印所有可用的浏览器信息
                    self.logger.info("\n可用的浏览器实例:")
                    for i, browser in enumerate(browsers, 1):
                        self.logger.info(f"{i}. ID: {browser['id']}")
                        self.logger.info(f"   名称: {browser['name']}")
                        self.logger.info(f"   备注: {browser['remark']}")
                        self.logger.info(f"   PID: {browser['pid']}")
                    
                    # 让用户选择浏览器
                    browser_id = browsers[0]['id']  # 默认使用第一个
            
            # 检查是否已经连接到这个浏览器
            if browser_id in self.active_drivers:
                driver = self.active_drivers[browser_id]
                # 创建新标签页
                if url:
                    driver.execute_script("window.open('about:blank', '_blank');")
                    time.sleep(self.tab_switch_wait)
                    driver.switch_to.window(driver.window_handles[-1])
                    driver.get(url)
                return driver
                
            # 连接到新的浏览器实例
            response = requests.post(
                f"{self.url}/browser/open",
                headers=self.headers,
                data=json.dumps({
                    "id": browser_id,
                    "queue": True
                })
            )
            
            response_json = response.json()
            if response_json.get('success'):
                data = response_json['data']
                ws_address = data.get('http')
                driver_path = data.get('driver')
                
                chrome_options = webdriver.ChromeOptions()
                chrome_options.add_experimental_option("debuggerAddress", ws_address)
                
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                
                # 设置等待时间
                driver.set_page_load_timeout(self.page_load_timeout)
                driver.implicitly_wait(self.implicit_wait)
                
                # 保存到活动实例字典
                driver.browser_id = browser_id
                self.active_drivers[browser_id] = driver
                
                # 如果提供了URL，打开页面
                if url:
                    driver.get(url)
                    
                return driver
                
            return None
            
        except Exception as e:
            self.logger.error(f"连接浏览器失败: {str(e)}")
            return None

    def close_browser(self, browser_id):
        """关闭指定的浏览器实例"""
        try:
            if browser_id in self.active_drivers:
                driver = self.active_drivers[browser_id]
                driver.quit()
                del self.active_drivers[browser_id]
                
            requests.post(
                f"{self.url}/browser/close",
                headers=self.headers,
                data=json.dumps({"id": browser_id})
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"关闭浏览器失败: {str(e)}")
            return False

    def close_all_browsers(self):
        """关闭所有活动的浏览器实例"""
        for browser_id in list(self.active_drivers.keys()):
            self.close_browser(browser_id)

    def open_url_in_new_tab(self, driver, url):
        """在指定浏览器的新标签页中打开URL"""
        try:
            # 创建新标签页
            driver.execute_script("window.open('about:blank', '_blank');")
            time.sleep(self.tab_switch_wait)
            
            # 切换到新标签页
            driver.switch_to.window(driver.window_handles[-1])
            
            # 访问URL
            self.logger.info(f"正在导航到: {url}")
            driver.get(url)
            
            # 等待页面加载
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                self.logger.info(f"成功加载页面: {url}")
                return True
            except Exception as e:
                self.logger.error(f"页面加载超时: {str(e)}")
                return False
            
        except Exception as e:
            self.logger.error(f"打开新标签页失败: {str(e)}")
            return False

    def get_active_tabs(self, driver):
        """获取浏览器的所有活动标签页"""
        return driver.window_handles

    def switch_to_tab(self, driver, index=-1):
        """切换到指定的标签页，默认切换到最后一个"""
        try:
            handles = driver.window_handles
            if handles:
                driver.switch_to.window(handles[index])
                return True
            return False
        except Exception as e:
            self.logger.error(f"切换标签页失败: {str(e)}")
            return False