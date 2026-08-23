"""Offline demo: runs the full pipeline with mock LLMs (no API keys needed)."""
import os

os.environ.setdefault("GENERATOR_PROVIDER", "mock")
os.environ.setdefault("JUDGE_PROVIDER", "mock")

from app.pipeline import Pipeline  # noqa: E402

BASE = ("أعلنت وزارة الطاقة السعودية اليوم عن إطلاق مشروع جديد للطاقة الشمسية "
        "بقدرة 2000 ميجاواط في منطقة الجوف، باستثمارات تبلغ 5 مليار ريال. "
        "وقال المتحدث الرسمي إن المشروع سيوفر 3000 وظيفة جديدة ويساهم في خفض "
        "الانبعاثات الكربونية بنسبة 15% بحلول عام 2030.")

ARTICLES = [
    {"id": "a1", "source": "alarabiya", "url": "https://example.com/1",
     "title": "مشروع طاقة شمسية جديد في الجوف", "text": BASE, "published_ts": 1000},
    {"id": "a2", "source": "spa", "url": "https://example.com/2",
     "title": "مشروع طاقة شمسية جديد في الجوف", "text": BASE, "published_ts": 1001},
    {"id": "a3", "source": "okaz", "url": "https://example.com/3",
     "title": "إطلاق مشروع للطاقة الشمسية بقدرة 2000 ميجاواط",
     "text": BASE.replace("اليوم", "صباح اليوم").replace("وقال المتحدث الرسمي", "وأوضح المتحدث الرسمي"),
     "published_ts": 1002},
    {"id": "a4", "source": "bloomberg", "url": "https://example.com/4",
     "title": "أسواق النفط تستقر",
     "text": ("استقرت أسعار النفط العالمية اليوم عند مستوى 82 دولارًا للبرميل وسط ترقب "
              "المستثمرين لقرارات أوبك بلس المقبلة بشأن مستويات الإنتاج خلال الربع الأخير."),
     "published_ts": 1003},
]

if __name__ == "__main__":
    stats = Pipeline(style="formal").run(ARTICLES)
    print(stats)
