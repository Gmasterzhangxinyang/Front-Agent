"""
Feedback form page for Streamlit — accessed via URL from Front comment.
"""
import streamlit as st
import requests
import json

st.set_page_config(page_title="评价 AI 回复", page_icon="📋")

st.title("📋 评价 AI 回复")

# Parse URL params
query_params = st.query_params
conv_id = query_params.get("conv", "")
category = query_params.get("category", "")
msg_id = query_params.get("msg", "")

if not conv_id:
    st.error("缺少 conversation_id 参数")
    st.stop()

st.markdown(f"**Conversation ID：** `{conv_id}`")
st.markdown(f"**Skill 分类：** `{category}`")

# Form inputs
score = st.slider("评分（0-10）", 0, 10, 5)
correct_reply = st.text_area("正确回复（选填）", height=100)
suggestion = st.text_area("修改建议（选填）", height=100)

submitted = st.button("提交评价")

if submitted:
    # POST to the feedback API endpoint
    feedback_data = {
        "conversation_id": conv_id,
        "category": category,
        "score": score,
        "correct_reply": correct_reply,
        "suggestion": suggestion,
    }

    try:
        # Try to reach the FastAPI backend
        response = requests.post(
            f"http://localhost:8000/feedback/submit",
            json=feedback_data,
            timeout=10,
        )
        if response.status_code == 200:
            st.success("✅ 评价已提交！系统将分析并生成修改建议。")
        else:
            st.error(f"❌ 提交失败：{response.status_code}")
    except Exception as e:
        st.error(f"❌ 无法连接后端服务：{e}")
        st.info("请确认 FastAPI 服务是否运行在 localhost:8000")
