from airbnb_calendar_checker import check_calendar_availability

def analyze_multiple_listings():
    # 要分析的Airbnb房源URL列表
    urls = [
        'https://www.airbnb.co.nz/rooms/837352260137971048',
        'https://www.airbnb.co.nz/rooms/another_room_id',
        # 添加更多URL...
    ]
    
    # 分析每个房源
    results = {}
    for url in urls:
        print(f"\n分析房源: {url}")
        calendar_data = check_calendar_availability(url)
        if calendar_data:
            results[url] = calendar_data
    
    return results

if __name__ == "__main__":
    results = analyze_multiple_listings()
    print("\n所有房源分析完成！") 