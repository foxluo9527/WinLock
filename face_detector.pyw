import cv2
import time
import pythoncom
import win32con
import win32gui
import win32ts
import ctypes
from threading import Event
import tkinter as tk
from tkinter import messagebox
import configparser
import pystray
from PIL import Image
import os
import socket

# 创建总日志文件夹
log_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
if not os.path.exists(log_folder):
    os.makedirs(log_folder)

# 定义一个函数来打印带时间戳的日志并写入文件
def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp}] {message}"
    print(formatted_message)

    # 获取当前日期和分钟
    current_date = time.strftime("%Y-%m-%d")
    current_minute = time.strftime("%Y-%m-%d_%H-%M")

    # 创建日期文件夹
    date_folder = os.path.join(log_folder, current_date)
    if not os.path.exists(date_folder):
        os.makedirs(date_folder)

    # 定义日志文件名
    log_file = os.path.join(date_folder, f"{current_minute}.log")

    # 将日志写入文件
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(formatted_message + "\n")

# 新增函数，用于动态获取资源文件的路径
def resource_path(relative_path):
    try:
        # PyInstaller 创建临时文件夹，将路径存储于 _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# 加载人脸检测器
face_cascade = cv2.CascadeClassifier(resource_path(os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')))

# 用于控制检测循环的事件
detection_paused = Event()

# 读取配置文件
config = configparser.ConfigParser()
config.read('config.ini')
if 'Settings' in config:
    interval = int(config['Settings'].get('interval', 30))
else:
    interval = 30
# 修改加载 DNN 人脸检测器的路径
net = cv2.dnn.readNetFromCaffe('deploy.prototxt.txt', 'res10_300x300_ssd_iter_140000.caffemodel')

def detect_face():
    log("开始尝试打开摄像头")
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        log("无法打开摄像头")
        return False
    log("摄像头已成功打开")

    # 读取一帧图像
    log("开始读取图像帧")
    ret, frame = cap.read()

    if ret:
        log("图像帧读取成功")
        (h, w) = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
        net.setInput(blob)
        log("开始进行人脸检测")
        detections = net.forward()

        # 释放摄像头资源
        cap.release()
        log("摄像头资源已释放")

        for i in range(0, detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            # 降低置信度阈值，例如从 0.5 降低到 0.3
            if confidence > 0.3:  
                log("检测到人脸")
                return True
        log("未检测到人脸")
        return False
    else:
        log("无法读取图像")
        cap.release()
        return False

def lock_screen():
    log("尝试锁屏")
    try:
        ctypes.windll.user32.LockWorkStation()
        log("锁屏成功")
    except Exception as e:
        log(f"锁屏失败: {e}")

# 新增全局变量，用于控制检测线程的运行
running = True

# 新增函数用于检查锁屏状态
def is_screen_locked():
    try:
        log("开始检查锁屏状态")
        session_info = win32ts.WTSEnumerateSessions(win32ts.WTS_CURRENT_SERVER_HANDLE)
        log(f"获取到的会话信息: {session_info}")

        # 遍历会话信息，找到 WinStationName 为 Console 的会话
        console_session = None
        for session in session_info:
            if session['WinStationName'] == 'Console':
                console_session = session
                break

        if console_session:
            log(f"找到 Console 会话: {console_session}")
            # 使用 WTS_SESSION_INFO_1 结构体获取更详细的会话信息
            session_info_1 = win32ts.WTSQuerySessionInformation(
                win32ts.WTS_CURRENT_SERVER_HANDLE,
                console_session['SessionId'],
                win32ts.WTSConnectState
            )
            log(f"Console 会话的连接状态: {session_info_1}")

            # 检查是否锁定，通常锁屏状态对应的连接状态是 WTSDisconnected 或 WTSIdle
            result = session_info_1 == win32ts.WTSDisconnected or session_info_1 == win32ts.WTSIdle
            log(f"锁屏检查结果: {result}")
            return result
        else:
            log("未找到 Console 会话，默认返回未锁定")
            return False

    except Exception as e:
        log(f"检查锁屏状态时出错: {e}")
    return False

def main():
    global interval, running
    log("人脸检测线程已启动")
    while running:
        # 检查是否暂停检测
        if detection_paused.is_set():
            time.sleep(1)
            continue

        # 检查是否锁屏
        # if is_screen_locked():
        #     time.sleep(1)
        #     continue
        
        # 执行人脸检测
        result = detect_face()

        if not result:
            log("未检测到人脸，即将锁屏")
            lock_screen()
        else:
            log("检测到人脸，不进行操作")

        # 等待指定时间间隔
        log(f"等待 {interval} 秒后进行下一次检测")
        time.sleep(interval)

# 新增变量，用于记录用户是否手动暂停检测
user_manually_paused = False

# 新增全局变量，用于记录锁屏状态
is_system_locked = False

# 手动定义 WTS 相关常量
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 7
WTS_SESSION_UNLOCK = 8

class SessionHandler:
    def __init__(self):
        log("初始化会话处理程序")
        self.hwnd = win32gui.CreateWindow("STATIC", "", 0, 0, 0, 0, 0, 0, 0, 0, None)
        win32gui.SetWindowLong(self.hwnd, win32con.GWL_WNDPROC, self.WndProc)

    def WndProc(self, hwnd, msg, wParam, lParam):
        global user_manually_paused, is_system_locked
        log(f"收到窗口消息: {msg}, wParam: {wParam}, lParam: {lParam}")
        try:
            if msg == WM_WTSSESSION_CHANGE:
                if wParam == WTS_SESSION_LOCK:
                    is_system_locked = True
                    log("系统已锁屏")
                elif wParam == WTS_SESSION_UNLOCK:
                    is_system_locked = False
                    log("系统已解锁")
        except Exception as e:
            log(f"处理 WTS 会话变更消息时出错: {e}")
        return win32gui.DefWindowProc(hwnd, msg, wParam, lParam)

class SettingsWindow(tk.Tk):
    def __init__(self):
        log("初始化设置窗口")
        super().__init__()
        self.title("设置")
        self.geometry("300x150")

        # 隐藏任务栏图标
        self.wm_attributes('-toolwindow', True)

        self.interval_label = tk.Label(self, text="识别间隔 (秒):")
        self.interval_label.pack(pady=10)

        self.interval_entry = tk.Entry(self)
        self.interval_entry.insert(0, str(interval))
        self.interval_entry.pack(pady=5)

        self.save_button = tk.Button(self, text="保存设置", command=self.save_settings)
        self.save_button.pack(pady=20)

        # 绑定最小化事件
        self.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.icon = None
        self.paused = False
        self.setup_tray_icon()

    def setup_tray_icon(self):
        log("开始设置托盘图标")
        try:
            # 这里需要一个图标文件，你可以替换为实际的图标路径
            image = Image.open('icon.png')
            self.menu_items = [
                pystray.MenuItem('显示窗口', lambda icon, item: self.show_window()),
                self.get_pause_resume_item(),
                pystray.MenuItem('退出', lambda icon, item: self.exit_app())
            ]
            menu = pystray.Menu(*self.menu_items)
            self.icon = pystray.Icon("name", image, "人脸检测设置", menu)
            self.icon.run_detached()
            log("托盘图标设置成功")
        except Exception as e:
            log(f"托盘图标设置失败: {e}")

    def show_window(self):
        log("显示设置窗口")
        try:
            # 检查窗口是否已经被销毁
            if not self._is_destroyed():
                # 使用 after 方法确保在主线程中执行
                self.after(0, self._safe_show_window)
        except Exception as e:
            log(f"调度显示窗口时出错: {e}")

    def _is_destroyed(self):
        try:
            self.winfo_exists()
            return False
        except tk.TclError:
            return True

    def _safe_show_window(self):
        try:
            # 确保窗口被正确显示
            if self.state() in ('withdrawn', 'iconic'):
                self.deiconify()
            # 确保窗口在最上层显示
            self.lift()
            self.attributes('-topmost', True)
            self.after(100, lambda: self.attributes('-topmost', False))
        except Exception as e:
            log(f"显示窗口时出错: {e}")

    def hide_window(self):
        log("隐藏设置窗口")
        try:
            # 确保窗口被正确隐藏
            self.withdraw()
        except Exception as e:
            log(f"隐藏窗口时出错: {e}")

    def get_pause_resume_item(self):
        if self.paused:
            return pystray.MenuItem('继续检测', self.resume_detection)
        else:
            return pystray.MenuItem('停止检测', self.pause_detection)

    def exit_app(self):
        import os
        os._exit(0)
        
    def save_settings(self):
        global interval
        log("开始保存设置")
        try:
            new_interval = int(self.interval_entry.get())
            if new_interval > 0:
                interval = new_interval
                config['Settings'] = {'interval': str(interval)}
                with open('config.ini', 'w') as configfile:
                    config.write(configfile)
                messagebox.showinfo("成功", "设置已保存")
                log("设置保存成功")
            else:
                messagebox.showerror("错误", "间隔时间必须大于 0")
                log("设置保存失败: 间隔时间必须大于 0")
        except ValueError:
            messagebox.showerror("错误", "请输入有效的整数")
            log("设置保存失败: 输入无效")

    def pause_detection(self):
        global detection_paused, user_manually_paused
        log("用户手动暂停人脸检测")
        detection_paused.set()
        user_manually_paused = True
        self.paused = True
        self.update_menu()
        log("人脸检测已暂停")

    def resume_detection(self):
        global detection_paused, user_manually_paused
        log("用户手动恢复人脸检测")
        detection_paused.clear()
        user_manually_paused = False
        self.paused = False
        self.update_menu()
        log("人脸检测已恢复")

    def update_menu(self):
        log("开始更新托盘菜单")
        self.menu_items[1] = self.get_pause_resume_item()
        self.icon.menu = pystray.Menu(*self.menu_items)
        try:
            self.icon.update_menu()
            log("托盘菜单更新成功")
        except Exception as e:
            log(f"托盘菜单更新失败: {e}")

# 尝试创建一个本地套接字
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 9999))  # 绑定一个特定的端口
except OSError:
    print("程序已经在运行中，退出当前实例。")
    sys.exit(1)

if __name__ == "__main__":
    log("程序启动")
    # 初始化会话处理程序
    handler = SessionHandler()

    import threading
    global detection_thread
    # 启动检测线程
    detection_thread = threading.Thread(target=main)
    detection_thread.daemon = True
    detection_thread.start()

    # 显示设置窗口
    settings_window = SettingsWindow()

    # 进入消息循环
    log("进入消息循环")
    try:
        settings_window.mainloop()
    except Exception as e:
        log(f"消息循环出错: {e}")
    finally:
        log("消息循环已退出")
    # 退出消息循环
    try:
        log("尝试退出消息循环")
        pythoncom.CoUninitialize()
        log("消息循环已退出")
    except Exception as e:
        log(f"退出消息循环时出错: {e}")
    # 关闭套接字
    s.close()
