"""Review queue + quality dashboard. Run: streamlit run streamlit_app.py"""
import statistics

import streamlit as st

from app import config, db
from app.buffer_client import publish_post

st.set_page_config(page_title="ميديا - مراجعة المحتوى", layout="wide")
st.markdown("<style>.stApp {direction: rtl; text-align: right;}</style>",
            unsafe_allow_html=True)
st.title("لوحة مراجعة المحتوى الآلي")

conn = db.get_conn()
tab_review, tab_stats = st.tabs(["قائمة المراجعة", "مؤشرات الجودة"])


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
