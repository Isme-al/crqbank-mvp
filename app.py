import streamlit as st
import pandas as pd
import random
import time
import os
import stripe
from supabase import create_client, Client

# ── CONFIG ────────────────────────────────────────────
st.set_page_config(page_title="CRQBank", page_icon="📚", layout="wide")

# ── CACHED DATA LOADER ─────────────────────────────────
@st.cache_data
def load_questions(path: str) -> pd.DataFrame:
    return pd.read_csv(path)

# ── SESSION STATE INITIALIZER ──────────────────────────
def init_state():
    defaults = {
        "user": None,
        "paid": False,
        "total": 0,
        "correct": 0,
        "start_time": None,
        "question_list": [],
        "current_q_idx": 0,
        "responses": [],
        "locked_mode": None,
        "locked_test_mode": None,
        "test_submitted": False,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

# ── SUPABASE AUTH SETUP ───────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = get_supabase()

def sign_up(email: str, password: str):
    return supabase.auth.sign_up({"email": email, "password": password})

def sign_in(email: str, password: str):
    return supabase.auth.sign_in_with_password({"email": email, "password": password})

# ── STRIPE SETUP ──────────────────────────────────────
stripe.api_key       = st.secrets["stripe_secret_key"]
PRICE_ID             = st.secrets["STRIPE_PRICE_ID"]
APP_BASE_URL         = st.secrets["APP_URL"]

def create_checkout_session():
    sess = stripe.checkout.Session.create(
        customer_email=st.session_state.user.email,
        line_items=[{"price": PRICE_ID, "quantity": 1}],
        mode="payment",
        success_url=f"{APP_BASE_URL}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=APP_BASE_URL,
    )
    return sess.url

def require_paid():
    params = st.experimental_get_query_params()
    if "session_id" in params:
        session = stripe.checkout.Session.retrieve(params["session_id"][0])
        if session.payment_status == "paid":
            st.session_state.paid = True
            supabase.table("users")\
                .update({"paid": True})\
                .eq("id", st.session_state.user.id)\
                .execute()
            st.experimental_rerun()

    if not st.session_state.paid:
        url = create_checkout_session()
        st.sidebar.markdown("### 🔒 Subscriber Access")
        st.sidebar.markdown(f"[Subscribe for $39]({url})")
        st.stop()

# ── PAGE RENDERERS ────────────────────────────────────
def render_auth(_):
    st.markdown("# Welcome to CRQBank")
    mode = st.radio("Choose an option", ["Log In", "Sign Up"])
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button(mode):
        if not email or not password:
            st.error("Enter both email & password.")
            return
        res = sign_up(email, password) if mode == "Sign Up" else sign_in(email, password)
        if getattr(res, "error", None):
            st.error(res.error.message)
        else:
            st.success(f"{mode} successful!")
            st.session_state.user = res.user

def render_home(df):
    if not st.session_state.user:
        st.error("🔒 Please log in on the Auth page.")
        return

    st.markdown("<h1>CRQBank Topics</h1>", unsafe_allow_html=True)
    st.write("Choose a topic below or start practicing from the sidebar.")

    # Get topic counts as a list of tuples
    topic_counts = list(df["topic"].value_counts().items())
    num_topics = len(topic_counts)

    # Split into two roughly equal columns
    half = (num_topics + 1) // 2
    col1_topics = topic_counts[:half]
    col2_topics = topic_counts[half:]

    col1, col2 = st.columns(2)
    with col1:
        for topic, cnt in col1_topics:
            st.markdown(f"- **{topic}** ({cnt} questions)")
    with col2:
        for topic, cnt in col2_topics:
            st.markdown(f"- **{topic}** ({cnt} questions)")

def render_practice(df):
    if not st.session_state.user:
        st.error("🔒 Please log in on the Auth page.")
        return
    st.markdown("<h1>Practice Questions</h1>", unsafe_allow_html=True)

    # Sidebar controls
    mode      = st.sidebar.selectbox("Mode", ["Free Trial", "Full Quiz"])
    test_mode = st.sidebar.radio("Test Mode", ["Tutor", "Test"])
    topics    = ["All"] + sorted(df["topic"].unique())
    chosen    = st.sidebar.selectbox("Topic", topics)

    if not st.session_state.locked_mode:
        def start_test():
            subset = df if chosen == "All" else df[df["topic"] == chosen]
            ids = subset.index.tolist()
            random.shuffle(ids)
            if mode == "Free Trial":
                ids = ids[:50]
            st.session_state.update({
                "locked_mode":      mode,
                "locked_test_mode": test_mode,
                "question_list":    ids,
                "responses":        [],
                "current_q_idx":    0,
                "total":            0,
                "correct":          0,
                "test_submitted":   False
            })
            if test_mode == "Test":
                st.session_state.start_time = time.time()

        st.sidebar.button("Start Test", on_click=start_test)
        st.stop()

    if st.session_state.locked_mode == "Full Quiz":
        require_paid()

    # Current question
    ids   = st.session_state.question_list
    idx   = st.session_state.current_q_idx
    total = len(ids)
    q     = df.loc[ids[idx]]
    tm    = st.session_state.locked_test_mode

    st.markdown(f"<div class='question-header'>Question {idx+1} of {total}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='question-text'>{q['question']}</div>", unsafe_allow_html=True)

    if tm == "Test":
        elapsed = int(time.time() - st.session_state.start_time)
        m, s = divmod(elapsed, 60)
        st.caption(f"Elapsed Time: {m:02d}:{s:02d}")

    if idx < len(st.session_state.responses):
        last = st.session_state.responses[idx]
        st.info(f"You selected **{last['selected']}**")
        if tm == "Tutor":
            with st.expander("Show Explanation"):
                st.markdown(f"**Answer:** {q['answer']}  ")
                st.markdown(f"**Explanation:** {q['explanation']}")
    else:
        for opt in ["a", "b", "c", "d"]:
            if st.button(f"{opt.upper()}. {q[f'option_{opt}']}", key=f"ans{idx}{opt}"):
                correct = (opt == q["answer"])
                st.session_state.total += 1
                if correct:
                    st.session_state.correct += 1
                st.session_state.responses.append({
                    "question": q["question"],
                    "selected": opt.upper(),
                    "correct": q["answer"].upper(),
                    "result":  "Correct" if correct else "Wrong"
                })
                # persist to Supabase
                try:
                    supabase.table("responses").insert({
                        "user_id":      st.session_state.user.id,
                        "question_idx": idx,
                        "question":     q["question"],
                        "selected":     opt.upper(),
                        "correct":      correct
                    }).execute()
                except Exception:
                    st.error("⚠️ Couldn’t save your answer.")
                st.rerun()

    # Navigation buttons
    c1, _, c3 = st.columns([1, 6, 1])
    with c1:
        if st.button("⬅️ Back", disabled=idx == 0):
            st.session_state.current_q_idx -= 1
            st.rerun()
    with c3:
        if st.button("➡️ Next", disabled=idx >= total - 1):
            st.session_state.current_q_idx += 1
            st.rerun()

    # Submit and results
    if len(st.session_state.responses) == total:
        st.divider()
        if st.button("🚀 Submit Test"):
            st.session_state.test_submitted = True
            st.rerun()

    if st.session_state.test_submitted:
        st.success("✅ Test submitted!")
        corr = st.session_state.correct
        acc  = (corr / total * 100) if total else 0
        st.write(f"**Total:** {total} | **Correct:** {corr} | **Accuracy:** {acc:.1f}%")
        st.table(pd.DataFrame(st.session_state.responses))
        if st.button("🔁 Restart"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

def render_stats(_):
    if not st.session_state.user:
        st.error("🔒 Please log in on the Auth page.")
        return
    data = supabase.table("responses")\
        .select("question_idx, correct, created_at")\
        .eq("user_id", st.session_state.user.id)\
        .order("created_at", desc=False)\
        .execute()
    rows = data.data or []
    total   = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    acc     = (correct / total * 100) if total else 0

    st.markdown("<h1>Your Progress</h1>", unsafe_allow_html=True)
    st.metric("Questions Attempted", total)
    st.metric("Correct Answers", correct)
    st.metric("Accuracy", f"{acc:.1f}%")

    if rows:
        hist = pd.DataFrame(rows)
        hist["cumulative_accuracy"] = hist["correct"].expanding().mean()
        hist.index = pd.to_datetime(hist["created_at"])
        st.line_chart(hist["cumulative_accuracy"], height=250, use_container_width=True)

# ── FINAL APP SETUP ───────────────────────────────────
base_dir = os.path.dirname(__file__)
df       = load_questions(os.path.join(base_dir, "questions.csv"))

with open("style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

init_state()

page = st.sidebar.radio("Navigation", ["Auth", "Home", "Practice", "Stats"])
PAGES = {
    "Auth":     render_auth,
    "Home":     render_home,
    "Practice": render_practice,
    "Stats":    render_stats,
}
PAGES[page](df)
