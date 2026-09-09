from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("PIL", filter=lambda name: name.endswith("ImagePlugin"))
