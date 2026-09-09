from multiprocessing import freeze_support

if __name__ == "__main__":
    # PyInstaller must dispatch worker/resource-tracker processes before our CLI
    # parses their internal Python arguments or initializes application services.
    freeze_support()

    from mdhelper.bootstrap.portable import main

    raise SystemExit(main())
