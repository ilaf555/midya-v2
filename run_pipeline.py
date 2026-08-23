"""نقطة تشغيل الخط من سطر الأوامر — يستخدمها cron و GitHub Actions.

    python run_pipeline.py

تغني عن إضافة كتلة __main__ داخل app/pipeline.py.
"""
from app.pipeline import fetch_and_run

if __name__ == "__main__":
    fetch_and_run()
