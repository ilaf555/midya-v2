"""Review queue + sources management + quality dashboard.
Run: streamlit run streamlit_app.py"""
import statistics

import streamlit as st

from app import config, db, sources as sources_mod
from app.buffer_client import publish_post

st.set_page_config(page_title="ميديا - مراجعة المحتوى", layout="wide")
st.markdown("<style>.stApp {direction: rtl; text-align: right;}</style>",
            unsafe_allow_html=True)
st.title("نظام المحتوى العربي الآلي")

conn = db.get_conn()
sources_mod.seed_defaults(conn)

tab_review, tab_sources, tab_stats = st.tabs(["قائمة المراجعة", "المصادر", "مؤشرات الجودة"])


def avg_score(g):
    vals = [v for v in g["judge_scores"].values() if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else 0.0


with tab_review:
    pending = db.list_generations(conn)
    if not pending:
        st.info("لا يوجد محتوى بانتظار المراجعة.")
    for g in pending:
        avg = avg_score(g)
        badge = "🟢" if g["status"] == "auto_approved" else ("🟡" if avg >= 3 else "🔴")
        with st.expander(f"{badge} {g['headline'] or '(بدون عنوان)'} — {avg:.1f}/5"):
            st.caption(f"المولّد: {g['generator_provider']} | المقيّم: {g['judge_provider']} | "
                       f"البرومبت: {g['prompt_version']} | التكلفة: ${g['cost_usd']}")
            st.write("**الملخص:**", g["summary"])
            edited = st.text_area("المنشور (قابل للتعديل)", g["post_text"], key=f"p{g['id']}")
            if g["unverified_claims"]:
                st.warning("ادعاءات غير مطابقة للمصدر: " + "، ".join(g["unverified_claims"]))
            if g["guardrail_reasons"]:
                st.error("ملاحظات الحواجز: " + "، ".join(g["guardrail_reasons"]))
            c1, c2, c3 = st.columns(3)
            if c1.button("اعتماد ونشر", key=f"a{g['id']}"):
                res = publish_post(edited)
                db.update_generation(conn, g["id"], "published", edited)
                st.success("تم النشر" if not res.get("dry_run") else "وضع التجربة: لم يُرسل فعليًا")
            if c2.button("حفظ كمسودة", key=f"s{g['id']}"):
                db.update_generation(conn, g["id"], "needs_review", edited)
                st.info("تم الحفظ")
            if c3.button("رفض", key=f"r{g['id']}"):
                db.update_generation(conn, g["id"], "rejected")
                st.warning("تم الرفض — أضفه كحالة اختبار دائمة")

with tab_sources:
    st.subheader("إضافة مصدر")
    with st.form("add_source"):
        c1, c2 = st.columns(2)
        name = c1.text_input("اسم المصدر")
        url = c2.text_input("رابط الخلاصة (RSS) أو النطاق (site)")
        c3, c4, c5 = st.columns(3)
        stype = c3.selectbox("النوع", ["rss", "site"])
        lang = c4.selectbox("اللغة", ["ar", "en"])
        category = c5.text_input("التصنيف", "Arabic News")
        credibility = st.slider("درجة المصداقية", 0.0, 1.0, 0.5, 0.1)
        if st.form_submit_button("إضافة"):
            source, errors = sources_mod.add_source(conn, {
                "name": name, "type": stype, "url": url,
                "category": category, "language": lang, "credibility": credibility})
            if errors:
                st.error(" | ".join(errors))
            else:
                st.success(f"أُضيف المصدر: {source['name']}")

    st.subheader("المصادر النشطة")
    for s in sources_mod.list_sources(conn):
        c1, c2 = st.columns([5, 1])
        c1.write(f"**{s['name']}** — {s['type']} — {s['category']} — {s['language']} "
                 f"— مصداقية {s['credibility']}")
        if c2.button("حذف", key=f"del_{s['id']}"):
            sources_mod.delete_source(conn, s["id"])
            st.rerun()

    st.subheader("جلب وتشغيل الخط")
    q = st.text_input("كلمة البحث (اختياري)")
    c1, c2 = st.columns(2)
    tf = c1.selectbox("الإطار الزمني", ["24h", "7d", "30d", "all"])
    deep = c2.checkbox("بحث معمّق في الأرشيف", value=False)
    if st.button("جلب وتشغيل"):
        from app.pipeline import Pipeline
        with st.spinner("يجلب المصادر ويعالجها..."):
            stats = Pipeline().fetch_and_run(query=q, timeframe=tf, deep_search=deep)
        st.json(stats)

with tab_stats:
    all_g = db.all_generations(conn)
    if all_g:
        scores = [avg_score(g) for g in all_g if g["judge_scores"]]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("إجمالي التوليدات", len(all_g))
        c2.metric("متوسط الجودة", f"{statistics.mean(scores):.2f}/5" if scores else "-")
        c3.metric("التكلفة الكلية $", f"{sum(g['cost_usd'] for g in all_g):.4f}")
        approved = sum(1 for g in all_g if g["status"] == "auto_approved")
        c4.metric("نسبة القبول الآلي", f"{100 * approved / len(all_g):.0f}%")
    else:
        st.info("شغّل خط المعالجة أولًا لعرض المؤشرات.")
