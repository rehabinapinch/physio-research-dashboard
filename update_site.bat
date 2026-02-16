@echo off
echo 🚀 Running the Trawler...
py trawler.py

echo 📦 Adding new research to the library...
git add weekly_research.json
git commit -m "Weekly Update: %date%"

echo 🌍 Pushing to live website...
git push

echo ✅ Done! Your website will update in ~60 seconds.
pause