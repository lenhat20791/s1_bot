@echo off
title Starting test_S1 
echo Starting bots at: %date% %time%
echo User: lenhat20791
echo Directory: C:\Users\nhat\Downloads\s1\s1

:: Change to the correct directory
cd /d C:\Users\nhat\Downloads\s1\s1

:: Start S1 in a new window
start "S1 Bot" cmd /k "pytest test_s1.py"


:: Wait for 2 seconds
timeout /t 2 /nobreak > nul

:: Close the batch file window
exit