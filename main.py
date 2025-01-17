from machine import I2C, Pin, Timer, RTC
import utime
import network, ntptime
from vl53l0x import VL53L0X
from enhanced_neopixel import EnhancedNeoPixel
import socket
import json
# LED初始化
led = Pin(8, Pin.OUT)
np = EnhancedNeoPixel(8)


# 时间同步设置
def set_time():
    time_zone_offset = 8 * 3600  # 设置时区偏移，对于中国为UTC+8
    ntp_servers = ['cn.pool.ntp.org', 'ntp1.aliyun.com', 'time.windows.com', 'pool.ntp.org']
    rtc = RTC()
    print('Before synchronized time:', rtc.datetime())
    while True:
        try:
            for server in ntp_servers:
                ntptime.host = server  # 设置 NTP 服务器
                ntptime.settime()
                print('Synchronized utc time:', rtc.datetime())
                current_time = utime.time() + time_zone_offset
                local_time = utime.localtime(current_time)
                # 将 local_time 转换为与 rtc.datetime() 兼容的格式
                rtc_time = (local_time[0], local_time[1], local_time[2], local_time[6] , local_time[3], local_time[4], local_time[5], 0)
                rtc.datetime(rtc_time)
                print('Synchronized time:', rtc.datetime())
                return
        except OSError:
            print('Failed to synchronize')
            utime.sleep(2)

# Wi-Fi连接函数
def connect_wifi(ssid, password):
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('Connecting to network...')
        sta_if.active(True)
        sta_if.connect(ssid, password)
        while not sta_if.isconnected():
            pass
    print('Network config:', sta_if.ifconfig())
    np.start_blinking('green', 1, brightness=0.5)
    set_time()
    np.stop_blinking()

connect_wifi('KuroGalaxy', '05722067')



# VL53L0X传感器初始化
i2c = I2C(0, scl=Pin(3), sda=Pin(4))
sensor = VL53L0X(i2c)

is_start_time = True # every time boot or start working
def is_within_active_hours(current_time):
    global is_start_time
    # 检测是否为工作日的有效工作时间
    hour = current_time[3]
    minute = current_time[4]
    weekday = current_time[6]
    if weekday >= 5:
        return False
    # 早上9点到晚上5点半，中午12到2点不记录
    if hour < 9 or hour > 17 or (hour == 17 and minute > 30):
        is_start_time = True
        return False
    # if hour == 11 and minute >= 30:
    #     return True
    if 12 <= hour < 14:
        is_start_time = True
        return False
    return True

# 数据记录
data_log = {'events': []}
try:
    with open('data_log.json', 'r') as f:
        data_log = json.load(f)
except Exception as e:
    print(f"Error loading data: {e}")

def update_log(sitting):
    global is_start_time
    timestamp = utime.time()  # 记录当前Unix时间戳

    event_type = 'sitting' if sitting else 'standing'

    if is_start_time or data_log['events'][-1]['type'] != event_type: # new event
        data_log['events'].append({'type': event_type, 'start': timestamp, 'end': timestamp})
        is_start_time = False
        print(f"Logged new {event_type} event from {timestamp}")
    # 更新正在进行的事件结束时间
    data_log['events'][-1]['end'] = timestamp
    # 持久化数据存储
    with open('data_log.json', 'w') as f:
        json.dump(data_log, f)

# 定时器和状态检查
sitting = False
start_time = 0

def set_sitting_alert_color(sitting_time):
    if sitting_time > 40:  # 40分钟
        np.start_blinking('red', 1, brightness=1)
    elif sitting_time > 30: 
        np.set_color("red", brightness=0.8)
    elif sitting_time > 20: 
        np.set_color("blue", brightness=0.5)
    elif sitting_time > 15: 
        np.set_color("cyan", brightness=0.5)
    else: 
        np.set_color("green", brightness=sitting_time/15.)

def check_sitting(_):
    global start_time, sitting
    if not is_within_active_hours(utime.localtime(utime.time())):
        return
    distance = sensor.read()
    print(f'Current distance: {distance} mm')
    if distance > 200 and sitting:
        sitting = False
        start_time = 0
        np.stop_blinking()
        np.clear()
        print(f"Transition to standing at {utime.time()}")
    elif distance < 200 and not sitting: # start sitting
        sitting = True
        start_time = utime.ticks_ms()
        print(f"Transition to sitting at {utime.time()}")
    elif distance < 200 and sitting:
        sitting_time = utime.ticks_diff(utime.ticks_ms(), start_time) / 1000 / 60 # minutes
        set_sitting_alert_color(sitting_time)
    update_log(sitting)
    


timer = Timer(2)
timer.init(period=2000, mode=Timer.PERIODIC, callback=check_sitting)

# 网页显示
def format_datetime(t):
    # t is a tuple: (year, month, day, hour, minute, second)
    return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"

def filter_events_by_date(data, target_date):
    filtered_events = []
    total_sitting, total_standing = 0, 0
    for event in data['events']:
        start_time = utime.localtime(event['start'])
        if start_time[:3] == target_date:
            if event['type'] == 'sitting':
                total_sitting += event['end'] - event['start']
            else:
                total_standing += event['end'] - event['start']
            filtered_events.append(event)
    return filtered_events, total_sitting, total_standing

def aggregate_data_by_day(data):
    daily_summary = {}
    for event in data['events']:
        start_time = utime.localtime(event['start'])
        event_date = start_time[:3]  # 取出年、月、日形成日期
        formatted_date = "{:04d}-{:02d}-{:02d}".format(*event_date)  # 格式化日期

        # 初始化日期键的站立和坐立时间
        if formatted_date not in daily_summary:
            daily_summary[formatted_date] = {'sitting': 0, 'standing': 0}

        # 根据事件类型增加对应的时间
        event_duration = event['end'] - event['start']
        if event['type'] == 'sitting':
            daily_summary[formatted_date]['sitting'] += event_duration
        else:
            daily_summary[formatted_date]['standing'] += event_duration

    return daily_summary

def generate_event_html(filtered_events):
    events_html = ""
    for event in filtered_events:
        start_time = utime.localtime(event['start'])
        end_time = utime.localtime(event['end'])
        duration = event['end'] - event['start']
        stime = format_datetime(start_time)
        etime = format_datetime(end_time)
        events_html += f"<tr><td>{event['type']}</td><td>{stime}</td><td>{etime}</td><td>{int(duration / 6)/10}min</td></tr>"
    return events_html

def generate_summary_html(daily_summary):
    summary_html = "<table><tr><th>Date</th><th>Total Sitting Time</th><th>Total Standing Time</th></tr>"
    for date, times in daily_summary.items():
        summary_html += f"<tr><td>{date}</td><td>{int(times['sitting'] / 3600)}h {int(times['sitting'] % 3600 / 60)}min</td><td>{int(times['standing'] / 3600)}h {int(times['standing'] % 3600 / 60)}min</td></tr>"
    summary_html += "</table>"
    return summary_html

def web_page():
    current_date = utime.localtime()[:3]  # (year, month, day)
    data = data_log
    try:
        filtered_events, total_sitting, total_standing = filter_events_by_date(data, current_date)
        events_html = generate_event_html(filtered_events)
        daily_summary = aggregate_data_by_day(data)
        summary_html = generate_summary_html(daily_summary)
        formatted_current_time = format_datetime(utime.localtime())
        status = "Sitting" if sitting else "Standing"
        html = f"""<html><head><title>ESP32 Sit Stand Alert</title>
                   <style>
                       table, th, td {{border: 1px solid black; border-collapse: collapse;}}
                       th, td {{padding: 8px; text-align: left;}}
                   </style>
                   </head>
                   <body>
                   <h1>Status: {status}</h1>
                   <p>Current Time: {formatted_current_time}</p>
                   <h2>Daily Summary</h2>
                   {summary_html}
                   <h2>Details for Today</h2>
                   <p>Total Sitting Time Today: {int(total_sitting / 3600)} hours, {int(total_sitting % 3600 / 60)} minutes</p>
                   <p>Total Standing Time Today: {int(total_standing / 3600)} hours, {int(total_standing % 3600 / 60)} minutes</p>
                   <table>
                       <tr><th>Type</th><th>Start Time</th><th>End Time</th><th>Duration</th></tr>
                       {events_html}
                   </table>
                   </body></html>"""
        return html
    except Exception as e:
        print(f"Error generating web page: {e}")
        return f"<html><body><h1>Error in generating data</h1><p>{e}<p></body></html>"
    
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(('', 80))
s.listen(5)

led.on() # initialize finished
while True:
    try:
        conn, addr = s.accept()
        request = conn.recv(1024)
        conn.send('HTTP/1.1 200 OK\n')
        conn.send('Content-Type: text/html\n')
        conn.send('Connection: close\n\n')
        conn.sendall(web_page())
        conn.close()
    except Exception as e:
        print(f"Error handling request: {e}")