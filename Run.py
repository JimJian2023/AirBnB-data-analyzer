import schedule
import time
import psutil
import sys
import os
import logging
from datetime import datetime
import advanced_analyzer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def is_analyzer_running():
    """检查advanced_analyzer.py是否正在运行"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # 检查进程的命令行参数
            if proc.info['cmdline'] and 'python' in proc.info['cmdline'][0].lower():
                cmdline = ' '.join(proc.info['cmdline'])
                if 'advanced_analyzer.py' in cmdline:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def run_analyzer():
    """运行数据分析任务"""
    logger.info("准备运行数据分析任务...")
    
    # 检查是否已有实例���运行
    if is_analyzer_running():
        logger.info("发现advanced_analyzer.py正在运行，等待其完成...")
        while is_analyzer_running():
            time.sleep(60)  # 每分钟检查一次
        logger.info("之前的实例已结束")
    
    try:
        logger.info("开始运行数据分析任务")
        advanced_analyzer.main()
        logger.info("数据分析任务完成")
    except Exception as e:
        logger.error(f"运行数据分析任务时发生错误: {str(e)}")

def main():
    """主函数"""
    # 设置固定运行时间为凌晨1:00
    run_time = "01:00"
    
    # 设置定时任务
    schedule.every().day.at(run_time).do(run_analyzer)
    logger.info(f"已设置在每天 {run_time} 运行数据分析任务")
    
    print(f"\n调度器已启动，将在每天 {run_time} 运行")
    print("程序将持续运行。按 Ctrl+C 终止程序。")
    
    # 主循环
    try:
        while True:
            # 计算距离下次运行的时间
            next_run = schedule.next_run()
            if next_run:
                time_diff = next_run - datetime.now()
                hours = int(time_diff.total_seconds() // 3600)
                minutes = int((time_diff.total_seconds() % 3600) // 60)
                seconds = int(time_diff.total_seconds() % 60)
                
                # 使用 \r 来实现同行刷新
                print(f"\r距离下次运行还有: {hours:02d}:{minutes:02d}:{seconds:02d}", end="", flush=True)
            
            schedule.run_pending()
            time.sleep(1)  # 改为每秒更新一次倒计时
    except KeyboardInterrupt:
        print("\n")  # 添加换行，使得终止信息显示在新行
        logger.info("程序被用户终止")
        print("程序已终止")

if __name__ == "__main__":
    main() 