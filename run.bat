@echo off
echo Checking Python installation...
python --version
if errorlevel 1 (
    echo Python is not installed or not in PATH
    pause
    exit /b 1
)

echo Checking required packages...
pip list | findstr "flask torch torchvision pillow pymongo python-dotenv pyjwt werkzeug requests"
if errorlevel 1 (
    echo Installing required packages...
    pip install -r requirements.txt
)

echo Checking for model file...
if not exist "final_model.pth" (
    echo Error: final_model.pth not found!
    echo Please make sure the model file is in the same directory as main.py
    pause
    exit /b 1
)

echo Starting Vikarshan Plant Disease Prediction Application...
echo Press Ctrl+C to stop the server
echo.
echo The application will be available at:
echo http://localhost:5000
echo.
echo If the page is not loading, check if:
echo 1. The port 5000 is not in use by another application
echo 2. Your firewall is not blocking the connection
echo 3. The model file is properly loaded
echo.
python main.py
if errorlevel 1 (
    echo.
    echo Error starting the application. Please check the error message above.
    pause
    exit /b 1
)
pause 