@echo off
setlocal
cd /d "%~dp0"
if not exist .venv (
  echo Python environment bana rahe hain...
  py -m venv .venv
  if errorlevel 1 (echo Python install nahi hai. python.org se Python 3 install karein aur Add Python to PATH select karein.& pause & exit /b 1)
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
if errorlevel 1 (echo Setup mein error aya. Internet connection aur Python check karein.& pause & exit /b 1)
start "FNP Billing App" http://127.0.0.1:5000
 echo.
echo FNP Billing App chal raha hai.
echo Isi computer par: http://127.0.0.1:5000
echo Mobile/another PC par same Wi-Fi use karte huay is computer ka local IP use karein.
echo Is window ko khula rakhein. Band karne se app ruk jayegi.
python app.py
pause
