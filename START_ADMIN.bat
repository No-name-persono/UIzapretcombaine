@echo off
:: Zapret2 Manager — Запуск с правами администратора
:: Дважды кликните по этому файлу

title Zapret2 Manager

:: Проверяем права администратора
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Запрашиваем права администратора...
    powershell -Command "Start-Process cmd -ArgumentList '/c cd /d \"%~dp0\" && python \"%~dp0main.py\" && pause' -Verb RunAs"
    exit /b
)

:: Уже администратор
echo [*] Запущено от администратора
echo [*] Директория: %~dp0
echo.

cd /d "%~dp0"
python main.py

echo.
echo [*] Завершено. Если были ошибки - проверьте data\logs\
pause
