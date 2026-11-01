import keyboard
from ui import App


def main():
    app = App()

    def safe(fn):
        def handler(_e):
            app.after(0, fn)
        return handler

    keyboard.on_press_key("f8", safe(app.start), suppress=False)
    keyboard.on_press_key("f9", safe(app.toggle_pause), suppress=False)
    keyboard.on_press_key("esc", safe(app.stop), suppress=False)

    app.mainloop()
    keyboard.unhook_all()


if __name__ == "__main__":
    main()