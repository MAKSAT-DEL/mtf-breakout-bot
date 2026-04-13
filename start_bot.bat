@echo off
:restart
echo [%date% %time%] Bot başlatılıyor... >> bot_monitor.log
py live_bot.py >> bot_monitor.log 2>&1
echo [%date% %time%] Bot durdu, 30 sn sonra yeniden başlatılıyor... >> bot_monitor.log
timeout /t 30
goto restart