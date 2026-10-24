import launch

for package in ("aiohttp", "xmltodict", "furl"):
    if not launch.is_installed(package):
        launch.run_pip(f"install {package}", f"Gelbooru Prompt: {package}")

