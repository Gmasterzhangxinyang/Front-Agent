"""
Streamlit UI for Skill 自进化系统
"""
import streamlit as st
import asyncio
from datetime import datetime

# 必须先设置 page_config
st.set_page_config(page_title="Skill Evolution", layout="wide")

st.title("🧬 Skill 自进化系统")

# Sidebar: navigation
page = st.sidebar.radio(
    "导航",
    ["📋 待审批建议", "📁 Skill 列表", "⏪ 版本回退", "📊 完整日志"],
)


# ── Helper ──────────────────────────────────────────────────────────────
def run_sync(coro):
    """在 Streamlit 里运行 async 代码"""
    return asyncio.run(coro)


# ── Page 1: 待审批建议 ────────────────────────────────────────────────
if page == "📋 待审批建议":
    st.header("待审批建议")

    from services.skill_suggestion_store import skill_suggestion_store

    suggestions = run_sync(
        skill_suggestion_store.list_suggestions(status="pending", limit=100)
    )

    if not suggestions:
        st.info("暂无待审批建议")
    else:
        for sg in suggestions:
            with st.expander(
                f"**{sg['skill_name']}** · {sg['suggestion_type']} · "
                f"{sg['created_at'][:19] if sg['created_at'] else '无时间'}",
                expanded=False,
            ):
                col1, col2 = st.columns([1, 1])

                # Left: diff 可视化
                with col1:
                    st.markdown("### 🔴 已删除")
                    st.code(sg["deleted_content"] or "(无删除)", language="markdown")
                    st.markdown("### 🟢 已新增")
                    st.code(sg["added_content"] or "(无新增)", language="markdown")

                # Right: 完整内容 + 来源
                with col2:
                    st.markdown("### 📄 完整新内容")
                    st.text_area(
                        "完整 skill 内容",
                        value=sg["full_skill_content"] or "",
                        height=300,
                        disabled=True,
                        key=f"full_{sg['id']}",
                    )
                    st.markdown("### 💡 改动理由")
                    st.info(sg["reason"] or "无说明")

                    # Source examples
                    if sg["source_examples"]:
                        import json as _json

                        try:
                            src = _json.loads(sg["source_examples"])
                            st.markdown("### 📌 来源记录")
                            st.markdown(f"**用户问题：** {src.get('user_question', 'N/A')}")
                            st.markdown(f"**AI 原回答：** {src.get('ai_answer', 'N/A')}")
                            st.markdown(f"**Bobby 正确回复：** {src.get('bobby_corrected', 'N/A')}")
                            st.markdown(f"**评分：** {src.get('score', 'N/A')}/10")
                        except Exception:
                            pass

                # Buttons with lock check info
                btn_col1, btn_col2, status_col = st.columns([1, 1, 3])

                # Check if locked (simple approach: just show button)
                with btn_col1:
                    approved = st.button(
                        "✅ 通过",
                        key=f"approve_{sg['id']}",
                        help="更新 skill 文件并推送到 GitHub",
                    )
                with btn_col2:
                    rejected = st.button(
                        "❌ 否决",
                        key=f"reject_{sg['id']}",
                    )
                with status_col:
                    st.caption(f"ID: {sg['id']} · 提交者: {sg['submitted_by']}")

                if approved:
                    _suggestion_id = sg["id"]
                    _skill_name = sg["skill_name"]
                    _content = sg["full_skill_content"]
                    _reason = sg["reason"]

                    # Execute the skill update
                    from services.file_git import update_skill_file
                    from services.skill_suggestion_store import skill_suggestion_store as sss
                    from services.skill_version_store import skill_version_store

                    success, msg = run_sync(
                        update_skill_file(_skill_name, _content, f"feat(skills): update {_skill_name}.md")
                    )

                    if success:
                        run_sync(sss.approve(_suggestion_id, "bobby"))

                        # Check if we need to save a version snapshot
                        change_count = run_sync(
                            skill_version_store.increment_change_count(_skill_name)
                        )
                        if change_count >= 3:
                            run_sync(
                                skill_version_store.add_snapshot(
                                    _skill_name, _content, "ai"
                                )
                            )
                            st.success(f"✅ 已通过！并已保存版本快照（change_count={change_count}）")
                        else:
                            st.success(f"✅ 已通过！({msg})")
                        st.rerun()
                    else:
                        st.error(f"❌ 提交失败：{msg}")

                if rejected:
                    run_sync(
                        skill_suggestion_store.delete(sg["id"])
                    )
                    st.rerun()


# ── Page 2: Skill 列表 ─────────────────────────────────────────────────
elif page == "📁 Skill 列表":
    st.header("📁 Skill 文件列表")

    from pathlib import Path

    skills_dir = Path(__file__).parent / "skills"
    skill_files = sorted(skills_dir.glob("*.md"))

    for f in skill_files:
        name = f.stem
        with st.expander(f"**{name}** · {f.stat().st_size} bytes"):
            content = f.read_text(encoding="utf-8")
            st.text_area(
                f"内容 - {name}",
                value=content,
                height=400,
                disabled=True,
                key=f"skill_view_{name}",
            )


# ── Page 3: 版本回退 ──────────────────────────────────────────────────
elif page == "⏪ 版本回退":
    st.header("⏪ 版本回退")

    skill_names = [
        "classify",
        "technical",
        "account",
        "billing",
        "education",
        "purchase",
        "partnership",
        "security",
        "spam",
        "legal",
        "roadmap",
        "data_export",
        "unclear",
    ]
    selected_skill = st.selectbox("选择 Skill", skill_names)

    from services.skill_version_store import skill_version_store

    versions = run_sync(
        skill_version_store.list_versions(skill_name=selected_skill, limit=50)
    )

    if not versions:
        st.info(f"暂无 {selected_skill} 的版本记录")
    else:
        st.markdown(f"**{selected_skill}** 共 {len(versions)} 个版本")
        for v in versions:
            with st.expander(
                f"v{v['version']} · change_count={v['change_count']} · "
                f"{v['created_at'][:19] if v['created_at'] else 'N/A'}",
            ):
                st.text_area(
                    f"版本 {v['version']} 内容",
                    value=v["content"] or "",
                    height=300,
                    disabled=True,
                    key=f"version_view_{v['id']}",
                )
                if st.button("回退到此版本", key=f"rollback_{v['id']}"):
                    from services.file_git import rollback_skill_file

                    success, msg = run_sync(
                        rollback_skill_file(
                            selected_skill,
                            v["version"],
                            v["content"],
                        )
                    )
                    if success:
                        st.success(f"✅ 已回退到 v{v['version']}")
                    else:
                        st.error(f"❌ 回退失败：{msg}")


# ── Page 4: 完整日志 ──────────────────────────────────────────────────
elif page == "📊 完整日志":
    st.header("📊 完整日志")

    from services.skill_feedback_store import skill_feedback_store

    feedbacks = run_sync(
        skill_feedback_store.list_feedback(limit=200)
    )

    if not feedbacks:
        st.info("暂无反馈记录")
    else:
        st.markdown(f"共 {len(feedbacks)} 条记录")

        # Score stats
        skill_names = set(fb["skill_name"] for fb in feedbacks)
        st.markdown("### 平均分（按 Skill）")
        avg_data = []
        for sn in sorted(skill_names):
            avg = run_sync(skill_feedback_store.get_avg_score(sn))
            avg_data.append({"skill": sn, "avg_score": f"{avg:.1f}" if avg else "N/A"})

        if avg_data:
            import pandas as pd

            st.dataframe(pd.DataFrame(avg_data))

        st.markdown("### 反馈列表")
        for fb in feedbacks[:50]:
            color = (
                "🔴"
                if fb["score"] and fb["score"] <= 3
                else "🟡" if fb["score"] and fb["score"] <= 6 else "🟢"
            )
            with st.expander(
                f"{color} **{fb['skill_name']}** · {fb['score']}/10 · "
                f"{fb['created_at'][:19] if fb['created_at'] else 'N/A'}",
            ):
                st.markdown(f"**用户问题：** {fb['user_question']}")
                st.markdown(f"**AI 回答：** {fb['ai_answer']}")
                st.markdown(f"**Bobby 正确回复：** {fb['bobby_corrected_answer']}")
                st.markdown(f"**建议：** {fb['bobby_suggestion']}")
                st.markdown(f"**评分：** {fb['score']}/10")
