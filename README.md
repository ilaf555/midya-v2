# ميديا v2 — نظام المحتوى العربي الآلي

أتمتة كاملة لدورة المحتوى الإخباري العربي: **جمع ← استخراج ← تنقية ← تلخيص ← تقييم ← مراجعة ← نشر**.

مبني بـ Python + Streamlit + نماذج لغوية (OpenAI / Anthropic / Gemini)، مع تخزين SQLite ونشر عبر Buffer.

---

## المزايا الرئيسية

- **جمع الأخبار**: قراءة مصادر RSS متعددة عبر feedparser مع تطبيع العناصر
- **النص الكامل**: استخراج متن المقال من رابط الخبر عبر trafilatura (دعم جيد للعربية)
- **إزالة التكرار**: كشف الأخبار المكررة بـ rapidfuzz، مع دعم embeddings متعددة اللغات (اختياري)
- **تجميع الأحداث**: دمج الأخبار التي تغطي الحدث نفسه في عنصر واحد (اختياري عبر hdbscan)
- **الصياغة العربية**: تلخيص وإعادة صياغة عبر OpenAI أو Anthropic أو Gemini
- **تقييم الجودة**: حكم آلي على المسودات مع قواعد ضبط وسلامة
- **واجهة مراجعة عربية**: مراجعة المسودات واعتمادها قبل النشر عبر Streamlit
- **النشر**: نشر على الشبكات الاجتماعية عبر Buffer
- **الجدولة**: تشغيل تلقائي عبر APScheduler أو cron النظام أو GitHub Actions

## كيف يعمل

يمر كل خبر عبر خط معالجة (pipeline) واحد:

1. **الجلب** — `fetcher.py` يقرأ خلاصات RSS المعرّفة في `sources.py` ويطبّع العناصر
2. **الإثراء** — `fulltext.py` يجلب النص الكامل لكل مقال من رابطه (متوازٍ، مع حد أقصى 8000 حرف لضبط تكلفة التوكنات)
3. **التنقية** — `dedup.py` يزيل التكرار، و`clustering.py` يجمع الأخبار المرتبطة بالحدث نفسه
4. **الصياغة** — `llm.py` يولّد مسودة عربية من النص الكامل، و`arabic.py` يعالج خصوصية النص العربي
5. **التقييم** — `judge.py` يقيّم جودة المسودة آليًا، و`guardrails.py` يطبّق قواعد السلامة
6. **التخزين** — `db.py` يحفظ كل شيء في SQLite مع حالة كل عنصر
7. **المراجعة** — `streamlit_app.py` يعرض المسودات للمراجعة والاعتماد اليدوي
8. **النشر** — `buffer_client.py` ينشر المعتمد على حساباتك عبر Buffer

الدالة `fetch_and_run` في `app/pipeline.py` تنفّذ جولة كاملة من هذا الخط، وهي ما يُجدول تلقائيًا.

## بنية المشروع

```
midya-v2/
├── app/
│   ├── fetcher.py            # جلب RSS وتطبيع العناصر
│   ├── fulltext.py           # استخراج النص الكامل (trafilatura)
│   ├── sources.py            # إدارة مصادر الأخبار
│   ├── dedup.py              # إزالة التكرار
│   ├── clustering.py         # تجميع الأحداث
│   ├── llm.py                # التكامل مع النماذج اللغوية
│   ├── judge.py              # تقييم جودة المسودات
│   ├── guardrails.py         # قواعد الضبط والسلامة
│   ├── arabic.py             # معالجة النصوص العربية
│   ├── db.py                 # تخزين SQLite
│   ├── models.py             # نماذج البيانات
│   ├── config.py             # الإعدادات
│   ├── scheduler.py          # جدولة APScheduler داخل التطبيق
│   └── buffer_client.py      # النشر عبر Buffer
├── scripts/
│   └── migrate_fulltext.py   # ترحيل قاعدة البيانات (أعمدة النص الكامل)
├── .github/workflows/
│   └── fetch.yml             # الجدولة السحابية عبر GitHub Actions
├── streamlit_app.py          # واجهة المراجعة والاعتماد
├── run_pipeline.py           # نقطة تشغيل سطر الأوامر
├── demo.py                   # تجربة سريعة
├── requirements.txt
└── .env.example
```

## المتطلبات

- Python 3.10 أو أحدث (يُنصح بـ 3.12)
- مفتاح API لواحد على الأقل من مزوّدي النماذج اللغوية
- حساب Buffer (للنشر فقط — يمكن العمل بدونه في وضع المراجعة)

## التثبيت

```bash
git clone https://github.com/ilaf555/midya-v2.git
cd midya-v2
python -m venv venv
source venv/bin/activate        # على Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## الإعداد

انسخ ملف البيئة واملأ مفاتيحك:

```bash
cp .env.example .env
```

| المتغير | الوظيفة | إلزامي؟ |
|---|---|---|
| `OPENAI_API_KEY` | التلخيص والتقييم عبر OpenAI | واحد من مزوّدي LLM على الأقل |
| `ANTHROPIC_API_KEY` | التلخيص والتقييم عبر Anthropic | واحد من مزوّدي LLM على الأقل |
| `GEMINI_API_KEY` | التلخيص والتقييم عبر Google Gemini | واحد من مزوّدي LLM على الأقل |
| `BUFFER_ACCESS_TOKEN` | النشر على الشبكات عبر Buffer | للنشر فقط |

## قاعدة البيانات

التخزين بـ SQLite. عند التحديث لنسخة تدعم النص الكامل، نفّذ الترحيل مرة واحدة (آمن للتكرار):

```bash
python scripts/migrate_fulltext.py --db data/midya.db --table articles
```

يضيف عمودَي `full_text` و`full_text_fetched_at` بعد التحقق من عدم وجودهما. عدّل مسار القاعدة واسم الجدول حسب إعدادك.

## التشغيل

```bash
streamlit run streamlit_app.py   # واجهة المراجعة والاعتماد
python run_pipeline.py           # جولة جلب ومعالجة واحدة من سطر الأوامر
python demo.py                   # تجربة سريعة
```

## الجدولة التلقائية

ثلاثة خيارات — **فعّل واحدًا فقط** حتى لا يتكرر الجلب:

| الخيار | الأنسب لـ | الملف |
|---|---|---|
| APScheduler داخل Streamlit | تطبيق يعمل باستمرار على جهازك | `app/scheduler.py` |
| cron النظام | خادم VPS دائم التشغيل | سطر crontab أدناه |
| GitHub Actions | تشغيل سحابي دون خادم | `.github/workflows/fetch.yml` |

### APScheduler (داخل التطبيق)

أضف في `streamlit_app.py`:

```python
import streamlit as st
from app.scheduler import start_scheduler

@st.cache_resource
def boot_scheduler():
    return start_scheduler(cron="*/30 * * * *")   # كل 30 دقيقة، توقيت الرياض

boot_scheduler()
```

### cron النظام

```cron
*/30 * * * * cd ~/midya-v2 && flock -n /tmp/midya.lock venv/bin/python run_pipeline.py >> logs/fetch.log 2>&1
```

### GitHub Actions

السير جاهز في `.github/workflows/fetch.yml` (كل 30 دقيقة + زر تشغيل يدوي). خطوتان مطلوبتان:

1. أضف المفاتيح في **Settings → Secrets and variables → Actions** بنفس الأسماء في الجدول أعلاه
2. جرّب يدويًا من **Actions → fetch-and-run → Run workflow** قبل الاعتماد على الجدول

ملاحظة: لأن القاعدة ملف SQLite محلي، يتضمن السير خطوة commit-back تحفظ القاعدة المحدّثة في المستودع بعد كل جولة — بدونها تبدأ كل جولة بقاعدة فارغة.

## الاعتماديات الاختيارية

`requirements.txt` يعمل بحد أدنى. لجودة كاملة، ألغِ تعليق الأسطر المناسبة:

| الاعتمادية | تفعّل |
|---|---|
| `beautifulsoup4` | البحث الاحتياطي في DuckDuckGo/Google عند غياب RSS |
| `scikit-learn` | embeddings احتياطية بـ TF-IDF |
| `sentence-transformers` | embeddings متعددة اللغات (مُوصى بها لدقة إزالة التكرار) |
| `hdbscan` | تجميع الأحداث (مُوصى به) |
| `openai` / `anthropic` / `google-generativeai` | مكتبات مزوّدي النماذج اللغوية |

## ملاحظات تشغيلية

- النص الكامل يُقص عند 8000 حرف قبل إرساله للنموذج — عدّل `MAX_CHARS` في `app/fulltext.py` حسب ميزانيتك
- جلب النص الكامل متوازٍ (5 عمال افتراضيًا) مع مهلة لطف بين الطلبات حتى لا تُحظر المصادر
- العناصر التي لديها `full_text` مسبقًا تُتخطى تلقائيًا، فإعادة الجولة لا تكرر الجلب
