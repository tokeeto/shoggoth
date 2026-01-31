import multiprocessing

from shoggoth.tool import run

if __name__ == "__main__":
    # Required for multiprocessing to work with frozen executables (PyInstaller)
    multiprocessing.freeze_support()
    run()
