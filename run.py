import sys
import os
import traceback

# 兼容 PyInstaller 打包环境与开发环境的路径获取
def get_base_path():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 打包后运行：返回 PyInstaller 的临时解压目录
        return sys._MEIPASS
    else:
        # 开发环境：返回当前脚本所在目录
        return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_path()
sys.path.insert(0, BASE_DIR)

# 定义资源路径，供后续 UI 代码使用
ICON_PATH = os.path.join(BASE_DIR, "icon.png")
UI_DIR = os.path.join(BASE_DIR, "func", "ui")

if __name__ == "__main__":
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-background-timer-throttling")
    try:
        from func.ui.ui import MainWindow
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QIcon
        
        app = QApplication(sys.argv)
        
        # 设置全局图标
        if os.path.exists(ICON_PATH):
            app.setWindowIcon(QIcon(ICON_PATH))
            
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
        
    except Exception:
        # 【关键修改】：将 error.log 写入 exe 所在的真实目录，而非临时解压目录
        log_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else BASE_DIR
        log_path = os.path.join(log_dir, "error.log")
        
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
            
        print(f"程序崩溃，错误信息已写入 {log_path}")
        input("按回车键退出...") # 保留控制台阻塞，防止闪退
