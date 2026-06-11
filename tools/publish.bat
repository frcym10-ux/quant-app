@echo off
rem Generate swing-trade report and deploy to Vercel (run by Task Scheduler)
rem Requires one-time "vercel login" beforehand
cd /d H:\quant-app
python -X utf8 tools\publish_report.py --deploy >> data\publish.log 2>&1
