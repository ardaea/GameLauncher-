@echo off
REM Oyun Launcher -> tek .exe  (launcher.py ve launcher_extras.py aynı klasörde olmalı)
REM Ana dosyanın adı launcher.py değilse aşağıdaki SCRIPT değerini değiştir.
set SCRIPT=launcher.py

python -m pip install --upgrade pyinstaller pillow pygame mutagen opencv-python yt-dlp imageio-ffmpeg

pyinstaller --noconfirm --clean --onefile --noconsole --name OyunLauncher ^
  --collect-all yt_dlp --collect-all imageio_ffmpeg --collect-all pygame ^
  --hidden-import mutagen --hidden-import launcher_extras ^
  %SCRIPT%

echo.
echo Bitti: dist\OyunLauncher.exe
echo Config, assets ve music klasorleri exe'nin yanina olusturulur.
pause
