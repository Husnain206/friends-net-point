@echo off
set "APPDIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$W=New-Object -ComObject WScript.Shell; $S=$W.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\\Friends Net Point.lnk'); $S.TargetPath='%APPDIR%run_windows.bat'; $S.WorkingDirectory='%APPDIR%'; $S.IconLocation='%APPDIR%static\\fnp-logo.jpg'; $S.Description='Friends Net Point Billing Software'; $S.Save()"
echo Desktop par Friends Net Point shortcut bana diya gaya hai.
pause
