import sys
from PySide6.QtWidgets import QApplication
from chat_src.gui.login_ui import LoginWindow

def main():
    app = QApplication(sys.argv)
    w = LoginWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()