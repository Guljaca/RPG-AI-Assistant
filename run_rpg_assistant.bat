@echo off
chcp 65001 >nul 2>&1
title RPG AI Assistant - проверка зависимостей

echo ===================================================
echo   RPG AI Assistant - проверка зависимостей
echo ===================================================
echo.

:: 1. Проверка Python
echo [1/3] Проверка Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Ошибка: Python не найден в PATH.
    echo Установите Python и добавьте его в PATH.
    pause
    exit /b 1
)
python --version

:: 2. Проверка pip
echo.
echo [2/3] Проверка pip...
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo pip не найден. Попытка установки...
    python -m ensurepip
    if errorlevel 1 (
        echo Не удалось установить pip.
        pause
        exit /b 1
    )
)

:: 3. Проверка и установка requests
echo.
echo [3/3] Проверка библиотеки requests...
python -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo requests не найдена. Установка...
    python -m pip install requests
    if errorlevel 1 (
        echo Ошибка при установке requests.
        pause
        exit /b 1
    )
    echo requests успешно установлена.
) else (
    echo requests уже установлена.
)

:: 4. Запуск GUI-приложения в фоне и закрытие консоли
echo.
echo Запуск RPG AI Assistant...
start /B python "Project_Py3_RPG_AI_main_Tools_version_V3.4.py" >nul 2>&1
exit