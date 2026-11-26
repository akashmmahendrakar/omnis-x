import streamlit as st
import plotly.express as px
from backend import database as db
from backend.conflicts import conflicts
from frontend.ui import show_df, show_fig


def render():
    tt = db.get_timetable(); cf = conflicts(tt)
    c = st.columns(5)
    c[0].metric("Students", db.count("students"))
    c[1].metric("Faculty", db.count("faculty"))
    c[2].metric("Rooms + Labs", db.rooms_and_labs_count())
    c[3].metric("Conflicts", len(cf))
    c[4].metric("Open incidents", db.count("incidents", "where status='Open'"))
    l, r = st.columns([1.4, 1])
    with l:
        st.markdown("#### Timetable")
        show_df(tt[["subject", "faculty", "place", "day", "time"]])
    with r:
        st.markdown("#### Students per department")
        show_fig(px.bar(db.students_per_department(), x="dept", y="students"))
    if cf.empty: st.success("No conflicts detected.")
    else: st.warning(f"{len(cf)} issue(s) need attention."); show_df(cf)
