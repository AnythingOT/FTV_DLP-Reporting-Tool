"""DataLogPro Report Tool - start here (python main.py, or the DLPReport.exe built by build.bat)."""

import logging


def main():
    from dlpreport.app_info import APP_NAME, VERSION
    from dlpreport.settings import log_path

    logging.basicConfig(filename=log_path(), level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("dlpreport")
    log.info("%s %s starting", APP_NAME, VERSION)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on high-DPI screens
    except Exception:
        pass

    import tkinter as tk
    from tkinter import messagebox

    from dlpreport.ui.main_window import App

    root = tk.Tk()

    def on_error(exc, value, tb):  # any unexpected error: log it and tell the user, never fail silently
        log.error("Unhandled error", exc_info=(exc, value, tb))
        messagebox.showerror(APP_NAME, f"Unexpected error: {value}\n\nDetails are in {log_path()}")

    root.report_callback_exception = on_error
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
