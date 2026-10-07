@echo off
title ReliefLink — Database Connection Test
set /p RELIEFLINK_DB_PASSWORD=Enter your PostgreSQL (pgAdmin) password: 
set /p TARGET_DB=Enter database name [press Enter for relief_db]: 
if not "%TARGET_DB%"=="" set RELIEFLINK_DB_NAME=%TARGET_DB%
python test_connection.py
pause

