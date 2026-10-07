@echo off
rem Lance le service (Windows) avec l'environnement Python du projet : http://127.0.0.1:4330/telephones/
cd /d "%~dp0.."
".venv\Scripts\python.exe" service\telephones.py
