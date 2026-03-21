"""📓 Journal — Notes & observations while trading"""

import streamlit as st
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="📓 Journal", layout="wide")
st.title("📓 Trading Journal")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
JOURNAL_DIR = BASE_DIR / "journal"
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

today = datetime.now().strftime("%Y-%m-%d")
today_file = JOURNAL_DIR / f"{today}.md"

# Quick note
st.subheader("Quick Note")
with st.form("quick_note"):
    note = st.text_area("Add observation", placeholder="MXN premium higher after 10 AM today...")
    tags = st.multiselect("Tags", ["#observation", "#trade", "#idea", "#risk", "#pattern", "#important"])
    submitted = st.form_submit_button("📝 Add Note")
    if submitted and note:
        timestamp = datetime.now().strftime("%H:%M")
        tag_str = " ".join(tags) if tags else ""
        entry = f"- **[{timestamp}]** {note} {tag_str}\n"

        with open(today_file, "a") as f:
            f.write(entry)
        st.success(f"Note added at {timestamp}")
        st.rerun()

st.divider()

# Today's journal
st.subheader(f"Today's Journal ({today})")
if today_file.exists():
    content = today_file.read_text()
    st.markdown(content)

    # Edit mode
    if st.checkbox("Edit journal"):
        edited = st.text_area("Edit", value=content, height=400)
        if st.button("Save"):
            today_file.write_text(edited)
            st.success("Saved!")
            st.rerun()
else:
    st.info("No journal for today yet. Add a note above or run `python tools/trading_journal.py`")

st.divider()

# Past journals
st.subheader("Past Journals")
journal_files = sorted(JOURNAL_DIR.glob("*.md"), reverse=True)

if journal_files:
    for f in journal_files[:14]:
        date_str = f.stem
        with st.expander(f"📅 {date_str}"):
            st.markdown(f.read_text())
else:
    st.info("No past journals found.")

# Stats
st.divider()
st.subheader("Journal Stats")
total_days = len(journal_files)
total_notes = 0
for f in journal_files:
    total_notes += f.read_text().count("- **[")

col1, col2 = st.columns(2)
with col1:
    st.metric("Journal Days", total_days)
with col2:
    st.metric("Total Notes", total_notes)
