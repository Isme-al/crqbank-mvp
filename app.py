import streamlit as st
import pandas as pd
import random
import time
import os

# ── CONFIG ────────────────────────────────────────────
st.set_page_config(page_title="CRQBank", page_icon="📚", layout="wide")

# ── LOAD DATA ────────────────────────────────────────────
base_dir = os.path.dirname(__file__)
csv_path = os.path.join(base_dir, "questions.csv")
df = pd.read_csv(csv_path)

# ── SESSION STATE INIT ────────────────────────────────
if "init" not in st.session_state:
    st.session_state.update({
        "paid": False,
        "total": 0,
        "correct": 0,
        "start_time": None,
        "question_list": [],
        "current_q_idx": 0,
        "responses": [],
        "locked_mode": None,
        "locked_test_mode": None,
        "confirm_submit": False,
        "test_submitted": False,
        "init": True
    })

# ── STRIPE SETUP (Skip if using Streamlit secrets UI) ───────────────
import stripe
stripe.api_key = st.secrets.get("stripe_secret_key")
stripe_public_link = "https://buy.stripe.com/3cI3cueq09Ec4jV1xrbo402"

def require_paid():
    if not st.session_state.paid:
        st.sidebar.markdown("### Subscriber Access")
        st.sidebar.markdown(f"[Subscribe for $39]({stripe_public_link})")
        st.stop()

# ── CUSTOM STYLES ─────────────────────────────────────
with open("style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ── PAGE NAVIGATION ───────────────────────────────
page = st.sidebar.radio("Navigation", ["Home", "Practice", "Stats"])

# ── HOME PAGE ──────────────────────────────────
if page == "Home":
    st.markdown("<h1>CRQBank Topics</h1>", unsafe_allow_html=True)
    st.write("Choose a topic below or start practicing from the sidebar.")
    for topic, cnt in df["topic"].value_counts().items():
        st.markdown(f"- **{topic}** ({cnt} questions)")

# ── PRACTICE PAGE ──────────────────────────────
elif page == "Practice":
    st.markdown("<h1>Practice Questions</h1>", unsafe_allow_html=True)

    if not st.session_state.locked_mode:
        mode = st.sidebar.selectbox("Mode", ["Free Trial", "Full Quiz"])
        test_mode = st.sidebar.radio("Test Mode", ["Tutor", "Test"])
        topics = ["All"] + sorted(df["topic"].unique())
        chosen_topic = st.sidebar.selectbox("Topic", topics)

        def start_test():
            subset = df if chosen_topic == "All" else df[df["topic"] == chosen_topic]
            ids = subset.index.tolist()
            random.shuffle(ids)
            if mode == "Free Trial":
                ids = ids[:5]
            st.session_state.locked_mode = mode
            st.session_state.locked_test_mode = test_mode
            st.session_state.question_list = ids
            st.session_state.responses = []
            st.session_state.current_q_idx = 0
            st.session_state.total = 0
            st.session_state.correct = 0
            st.session_state.test_submitted = False
            if test_mode == "Test":
                st.session_state.start_time = time.time()

        st.sidebar.button("Start Test", on_click=start_test)
        st.stop()

    if st.session_state.locked_mode == "Full Quiz":
        require_paid()

    ids = st.session_state.question_list
    curr_idx = st.session_state.current_q_idx
    total_q = len(ids)
    q = df.loc[ids[curr_idx]]
    test_mode = st.session_state.locked_test_mode

    st.markdown(f"<div class='question-header'>Question {curr_idx+1} of {total_q}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='question-text'>{q['question']}</div>", unsafe_allow_html=True)

    if test_mode == "Test":
        elapsed = int(time.time() - st.session_state.start_time)
        mins, secs = divmod(elapsed, 60)
        st.caption(f"Elapsed Time: {mins:02d}:{secs:02d}")

    if curr_idx < len(st.session_state.responses):
        last = st.session_state.responses[curr_idx]
        st.info(f"You selected **{last['selected']}**")
        if test_mode == "Tutor":
            with st.expander("Show Explanation"):
                st.markdown(f"**Answer:** {q['answer']}  ")
                st.markdown(f"**Explanation:** {q['explanation']}")
    else:
        for opt in ["a", "b", "c", "d"]:
            if st.button(f"{opt.upper()}. {q[f'option_{opt}']}", key=f"{curr_idx}{opt}"):
                is_corr = (opt == q['answer'])
                st.session_state.responses.append({
                    "question": q['question'],
                    "selected": opt.upper(),
                    "correct": q['answer'].upper(),
                    "result": "Correct" if is_corr else "Wrong"
                })
                st.session_state.total += 1
                if is_corr:
                    st.session_state.correct += 1
                st.rerun()

    col1, col2, col3 = st.columns([1, 6, 1])
    with col1:
        if st.button("⬅️ Back", disabled=curr_idx == 0):
            st.session_state.current_q_idx -= 1
            st.rerun()
    with col3:
        if st.button("➡️ Next", disabled=curr_idx >= total_q - 1):
            st.session_state.current_q_idx += 1
            st.rerun()

    if len(st.session_state.responses) == total_q:
        st.divider()
        if st.button("🚀 Submit Test"):
            st.session_state.test_submitted = True
            st.rerun()

    if st.session_state.test_submitted:
        st.success("✅ Test submitted!")
        st.subheader("Test Analysis")
        correct = st.session_state.correct
        accuracy = (correct / total_q * 100) if total_q else 0
        st.write(f"**Total Questions:** {total_q}  |  **Correct:** {correct}  |  **Accuracy:** {accuracy:.1f}%")
        st.table(pd.DataFrame(st.session_state.responses))
        if st.button("🔁 Restart"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

# ── STATS PAGE ───────────────────────────────
elif page == "Stats":
    st.markdown("<h1>Your Progress</h1>", unsafe_allow_html=True)
    st.metric("Questions Attempted", st.session_state.total)
    st.metric("Correct Answers", st.session_state.correct)
    acc = (st.session_state.correct / st.session_state.total * 100) if st.session_state.total else 0
    st.metric("Accuracy", f"{acc:.1f}%")
