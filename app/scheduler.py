"""جدولة fetch_and_run تلقائيًا داخل تطبيق Streamlit عبر APScheduler.

التثبيت:
    pip install apscheduler

التشغيل من streamlit_app.py (يُستدعى مرة واحدة فقط بفضل cache_resource):

    import streamlit as st
    from app.scheduler import start_scheduler

    @st.cache_resource
    def boot_scheduler():
        return start_scheduler(cron="*/30 * * * *")

    boot_scheduler()

ملاحظة: هذا الأسلوب يعمل ما دام تطبيق Streamlit يعمل. للتشغيل الدائم
بدون تطبيق مفتوح، استخدم cron النظام أو GitHub Actions (راجع fetch.yml).
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# عدّل مسار الاستيراد إذا كانت الدالة معرّفة في ملف آخر
from app.pipeline import fetch_and_run

log = logging.getLogger(__name__)


def start_scheduler(
    cron: str = "*/30 * * * *",
    timezone: str = "Asia/Riyadh",
) -> BackgroundScheduler:
    """يشغّل fetch_and_run حسب جدول cron (افتراضيًا كل 30 دقيقة)."""
    minute, hour, dom, month, dow = cron.split()

    sched = BackgroundScheduler(timezone=timezone)
    sched.add_job(
        fetch_and_run,
        CronTrigger(
            minute=minute, hour=hour, day=dom,
            month=month, day_of_week=dow, timezone=timezone,
        ),
        id="fetch_and_run",
        max_instances=1,        # يمنع التشغيل المتداخل إذا طالت الجولة
        coalesce=True,          # يدمج المواعيد الفائتة في تشغيل واحد
        misfire_grace_time=300, # يسمح باللحاق حتى 5 دقائق بعد الموعد
        replace_existing=True,
    )
    sched.start()
    log.info("scheduler started: cron=%r tz=%s", cron, timezone)
    return sched
