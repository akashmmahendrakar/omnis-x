import sqlite3, hashlib
from collections import deque
import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DB = "omnisx.db"
st.set_page_config(page_title="OMNIS-X | Campus Digital Twin", page_icon="🏫", layout="wide")
st.markdown("""<style>
[data-testid="stMetric"]{background:#fff;padding:14px;border-radius:12px;border:1px solid #e7ebf3;}
.hero{padding:20px 24px;border-radius:16px;background:linear-gradient(120deg,#102a43,#176b87);color:#fff;margin-bottom:16px;}
.hero h1{color:#fff;margin:0;font-size:2rem;} .hero p{color:#e5f3fa;margin:4px 0 0;}
</style><div class="hero"><h1>🏫 OMNIS-X</h1>
<p>Institutional Digital Twin · Conflict Detection · Cascading Failure Simulation · Recovery Planning</p></div>""",
            unsafe_allow_html=True)

# ---------- Streamlit version compatibility ----------
def _ver():
    out = []
    for p in st.__version__.split(".")[:2]:
        out.append(int("".join(ch for ch in p if ch.isdigit()) or 0))
    return tuple(out)
NEW = _ver() >= (1, 52)
def show_df(d): st.dataframe(d, hide_index=True, **({"width": "stretch"} if NEW else {"use_container_width": True}))
def show_ed(d, **k): return st.data_editor(d, **({"width": "stretch"} if NEW else {"use_container_width": True}), **k)
def show_fig(f): st.plotly_chart(f, **({"width": "stretch"} if NEW else {"use_container_width": True}))

# ---------- Database ----------
TABLES = ["users", "departments", "students", "faculty", "classrooms", "laboratories", "subjects", "courses",
          "timetables", "examinations", "transport", "hostels", "placements", "events", "infrastructure",
          "dependencies", "incidents", "simulations", "recovery_plans", "recovery_actions"]
SCHEMA = """
create table if not exists users(user_id integer primary key autoincrement,name text,email text,password_hash text,role text);
create table if not exists departments(department_id integer primary key autoincrement,department_name text);
create table if not exists students(student_id integer primary key autoincrement,name text,department_id integer,semester integer);
create table if not exists faculty(faculty_id integer primary key autoincrement,name text,department_id integer,availability text);
create table if not exists classrooms(room_id integer primary key autoincrement,room_name text,capacity integer,status text);
create table if not exists laboratories(lab_id integer primary key autoincrement,lab_name text,capacity integer,status text);
create table if not exists subjects(subject_id integer primary key autoincrement,subject_name text,department_id integer);
create table if not exists courses(course_id integer primary key autoincrement,subject_id integer,faculty_id integer);
create table if not exists timetables(timetable_id integer primary key autoincrement,course_id integer,room_id integer,lab_id integer,day text,time text);
create table if not exists examinations(exam_id integer primary key autoincrement,subject_id integer,exam_date text,hall_id integer);
create table if not exists transport(vehicle_id integer primary key autoincrement,route_id text,driver_id integer,status text);
create table if not exists hostels(hostel_id integer primary key autoincrement,room_id integer,capacity integer,status text);
create table if not exists placements(placement_id integer primary key autoincrement,company_name text,interview_date text);
create table if not exists events(event_id integer primary key autoincrement,event_name text,venue_id integer,event_date text);
create table if not exists infrastructure(asset_id integer primary key autoincrement,asset_name text,asset_type text,status text);
create table if not exists dependencies(dependency_id integer primary key autoincrement,source_id text,target_id text,weight real);
create table if not exists incidents(incident_id integer primary key autoincrement,asset_id text,severity text,status text);
create table if not exists simulations(simulation_id integer primary key autoincrement,incident_id integer,impact_summary text);
create table if not exists recovery_plans(plan_id integer primary key autoincrement,simulation_id integer,objective_score real);
create table if not exists recovery_actions(action_id integer primary key autoincrement,plan_id integer,action_description text);
"""
TT_SQL = """select t.timetable_id tid,s.subject_name subject,s.department_id dept,c.faculty_id fid,f.name faculty,
f.availability favail,t.room_id,t.lab_id,coalesce(r.room_name,l.lab_name) place,coalesce(r.status,l.status) pstatus,t.day,t.time
from timetables t join courses c on c.course_id=t.course_id join subjects s on s.subject_id=c.subject_id
join faculty f on f.faculty_id=c.faculty_id left join classrooms r on r.room_id=t.room_id
left join laboratories l on l.lab_id=t.lab_id"""

def q(sql, p=()):
    c = sqlite3.connect(DB)
    try: return pd.read_sql_query(sql, c, params=p)
    finally: c.close()

def run(sql, p=()):
    c = sqlite3.connect(DB); cur = c.execute(sql, p); c.commit(); i = cur.lastrowid; c.close(); return i

def seed(c):
    m = c.executemany
    h = lambda s: hashlib.sha256(s.encode()).hexdigest()
    m("insert into users(name,email,password_hash,role) values(?,?,?,?)",
      [("Admin", "admin@college.edu", h("admin123"), "admin"), ("Registrar", "reg@college.edu", h("reg123"), "staff")])
    m("insert into departments(department_name) values(?)", [("CSE",), ("ECE",), ("ISE",)])
    m("insert into students(name,department_id,semester) values(?,?,?)", [(f"Student {i+1}", i % 3 + 1, 3 + i % 2) for i in range(45)])
    m("insert into faculty(name,department_id,availability) values(?,?,?)",
      [("Dr. Meera", 2, "Available"), ("Mr. Arun", 1, "Available"), ("Ms. Kavya", 3, "Available"), ("Dr. Rao", 1, "Available")])
    m("insert into classrooms(room_name,capacity,status) values(?,?,?)", [("C101", 60, "Active"), ("C102", 55, "Active"), ("C103", 65, "Active"), ("C104", 50, "Active")])
    m("insert into laboratories(lab_name,capacity,status) values(?,?,?)", [("LAB1", 35, "Active"), ("LAB2", 32, "Active")])
    m("insert into subjects(subject_name,department_id) values(?,?)",
      [("Data Structures", 1), ("Networks", 2), ("DBMS Lab", 1), ("Python", 3), ("Mathematics", 1), ("AI Lab", 3)])
    m("insert into courses(subject_id,faculty_id) values(?,?)", [(1, 1), (2, 1), (3, 2), (4, 3), (5, 2), (6, 3)])
    m("insert into timetables(course_id,room_id,lab_id,day,time) values(?,?,?,?,?)",
      [(1, 1, None, "Monday", "09:00-10:00"), (2, 2, None, "Monday", "10:00-11:00"), (3, None, 1, "Monday", "10:00-12:00"),
       (4, 1, None, "Monday", "11:00-12:00"), (5, 3, None, "Monday", "12:00-13:00"), (6, None, 2, "Monday", "14:00-16:00")])
    m("insert into examinations(subject_id,exam_date,hall_id) values(?,?,?)", [(1, "2026-12-10", 3), (4, "2026-12-11", 1), (2, "2026-12-12", 3)])
    m("insert into transport(route_id,driver_id,status) values(?,?,?)", [("Route-1", 101, "Running"), ("Route-2", 102, "Running"), ("Route-3", 103, "Running")])
    m("insert into hostels(room_id,capacity,status) values(?,?,?)", [(101, 4, "Active"), (102, 4, "Active")])
    m("insert into placements(company_name,interview_date) values(?,?)", [("TechCorp", "2026-12-11")])
    m("insert into events(event_name,venue_id,event_date) values(?,?,?)", [("Annual Tech Fest", 3, "2026-12-10")])
    m("insert into infrastructure(asset_name,asset_type,status) values(?,?,?)", [("Main Power Supply", "Power", "Operational"), ("Campus WiFi", "Network", "Operational")])
    d = set()
    for tid, rid, lid, fid, did in c.execute("select t.timetable_id,t.room_id,t.lab_id,c.faculty_id,s.department_id from timetables t "
                                            "join courses c on c.course_id=t.course_id join subjects s on s.subject_id=c.subject_id"):
        if rid: d.add((f"room:{rid}", f"tt:{tid}", 1.0))
        if lid: d.add((f"lab:{lid}", f"tt:{tid}", 1.0))
        d.add((f"faculty:{fid}", f"tt:{tid}", 1.0)); d.add((f"tt:{tid}", f"dept:{did}", 0.8))
    for eid, did, hall in c.execute("select e.exam_id,s.department_id,e.hall_id from examinations e join subjects s on s.subject_id=e.subject_id"):
        d.add((f"room:{hall}", f"exam:{eid}", 1.0)); d.add((f"dept:{did}", f"exam:{eid}", 0.6))
    for eid, v in c.execute("select event_id,venue_id from events"): d.add((f"room:{v}", f"event:{eid}", 1.0))
    for pid, in c.execute("select placement_id from placements"):
        for k in (1, 2, 3): d.add((f"dept:{k}", f"placement:{pid}", 0.4))
    for vid, in c.execute("select vehicle_id from transport"): d.add((f"transport:{vid}", f"dept:{(vid-1)%3+1}", 0.6))
    for rid, in c.execute("select room_id from classrooms"): d.add(("infra:1", f"room:{rid}", 0.9))
    for lid, in c.execute("select lab_id from laboratories"): d.add(("infra:1", f"lab:{lid}", 0.9)); d.add(("infra:2", f"lab:{lid}", 0.7))
    m("insert into dependencies(source_id,target_id,weight) values(?,?,?)", sorted(d))

def init_db():
    c = sqlite3.connect(DB); c.executescript(SCHEMA)
    if c.execute("select count(*) from users").fetchone()[0] == 0: seed(c)
    c.commit(); c.close()
init_db()

# ---------- Logic ----------
def span(t):
    a, b = t.split("-"); f = lambda x: int(x[:2]) * 60 + int(x[3:5]); return f(a), f(b)
def clash(a, b):
    try: (a1, a2), (b1, b2) = span(a), span(b); return a1 < b2 and b1 < a2
    except Exception: return False

def conflicts(tt):
    out, rows = [], tt.to_dict("records")
    for i, a in enumerate(rows):
        if a["favail"] != "Available": out.append(("High", "Faculty unavailable", a["subject"], f'{a["faculty"]} is {a["favail"]}'))
        if a["pstatus"] != "Active": out.append(("High", "Place unavailable", a["subject"], f'{a["place"]} is {a["pstatus"]}'))
        for b in rows[i + 1:]:
            if a["day"] != b["day"] or not clash(a["time"], b["time"]): continue
            pair = f'{a["subject"]} ↔ {b["subject"]}'
            if a["place"] == b["place"]: out.append(("High", "Room double-booking", pair, f'{a["place"]} used twice'))
            if a["fid"] == b["fid"]: out.append(("High", "Faculty double-booking", pair, f'{a["faculty"]} in two places'))
            if a["dept"] == b["dept"]: out.append(("Medium", "Student clash", pair, "Same department cohort overlaps"))
    return pd.DataFrame(out, columns=["Severity", "Conflict", "Activities", "Explanation"])

def build_graph():
    G = nx.DiGraph()
    for _, r in q("select source_id,target_id,weight from dependencies").iterrows():
        G.add_edge(r["source_id"], r["target_id"], weight=float(r["weight"]))
    return G

def labels():
    L = {}
    for k, t, i, n in [("room", "classrooms", "room_id", "room_name"), ("lab", "laboratories", "lab_id", "lab_name"),
                       ("faculty", "faculty", "faculty_id", "name"), ("dept", "departments", "department_id", "department_name"),
                       ("infra", "infrastructure", "asset_id", "asset_name"), ("transport", "transport", "vehicle_id", "route_id"),
                       ("placement", "placements", "placement_id", "company_name"), ("event", "events", "event_id", "event_name")]:
        for _, r in q(f"select {i} a,{n} b from {t}").iterrows(): L[f"{k}:{r['a']}"] = str(r["b"])
    for _, r in q(TT_SQL).iterrows(): L[f"tt:{r['tid']}"] = f"{r['subject']} {r['day'][:3]} {r['time']}"
    for _, r in q("select e.exam_id a,s.subject_name b from examinations e join subjects s on s.subject_id=e.subject_id").iterrows():
        L[f"exam:{r['a']}"] = f"Exam: {r['b']}"
    return L

def cascade(G, start, thr):
    res = {start: (0, 1.0)}; dq = deque([start])
    while dq:
        n = dq.popleft(); d, s = res[n]
        for m in G.successors(n):
            s2 = s * G[n][m]["weight"]
            if s2 >= thr and (m not in res or s2 > res[m][1]): res[m] = (d + 1, s2); dq.append(m)
    return res

def make_plan(start, res, L):
    tt, acts, changes = q(TT_SQL), [], []
    kind, i = start.split(":"); i = int(i)
    size = {int(a): int(b) for a, b in q("select department_id,count(*) from students group by 1").values}
    resolved = total = 0
    if kind in ("room", "lab"):
        col = "room_id" if kind == "room" else "lab_id"
        pool = q("select room_id id,room_name name,capacity,status from classrooms") if kind == "room" else \
            q("select lab_id id,lab_name name,capacity,status from laboratories")
        for idx, r in tt[tt[col] == i].iterrows():
            total += 1; need = size.get(int(r["dept"]), 0); pick = None
            for _, p in pool.iterrows():
                if p["id"] == i or p["status"] != "Active" or p["capacity"] < need: continue
                busy = tt[(tt[col] == p["id"]) & (tt["day"] == r["day"]) & tt["time"].apply(lambda x: clash(x, r["time"]))]
                if busy.empty: pick = p; break
            if pick is not None:
                tt.at[idx, col] = pick["id"]; resolved += 1; changes.append((int(r["tid"]), col, int(pick["id"])))
                acts.append(f'Move {r["subject"]} ({r["day"]} {r["time"]}) from {r["place"]} to {pick["name"]}')
            else:
                acts.append(f'MANUAL REVIEW: no free room for {r["subject"]} ({r["day"]} {r["time"]})')
    elif kind == "faculty":
        fac = q("select faculty_id id,name,department_id dept,availability from faculty")
        for idx, r in tt[tt["fid"] == i].iterrows():
            total += 1; pick = None
            for _, p in fac.sort_values(by="dept", key=lambda s: s != r["dept"]).iterrows():
                if p["id"] == i or p["availability"] != "Available": continue
                busy = tt[(tt["fid"] == p["id"]) & (tt["day"] == r["day"]) & tt["time"].apply(lambda x: clash(x, r["time"]))]
                if busy.empty: pick = p; break
            if pick is not None:
                resolved += 1; acts.append(f'Assign substitute {pick["name"]} for {r["subject"]} ({r["day"]} {r["time"]})')
            else:
                acts.append(f'MANUAL REVIEW: no substitute for {r["subject"]} ({r["day"]} {r["time"]})')
    for n, (d, s) in sorted(res.items(), key=lambda x: x[1][0]):
        k = n.split(":")[0]
        if n != start and k in ("exam", "event", "placement"):
            acts.append(f'Review {k} "{L.get(n, n)}" (impact {s:.0%}): reschedule or relocate if required')
        if n != start and k == "dept":
            acts.append(f'Notify {L.get(n, n)} students and faculty of schedule changes')
    score = round(100 * resolved / total, 1) if total else 100.0
    return acts, changes, score

def plot_cascade(G, res, start, L):
    layers = {}
    for n, (d, s) in res.items(): layers.setdefault(d, []).append(n)
    pos = {n: (d, -(k - (len(ns) - 1) / 2)) for d, ns in layers.items() for k, n in enumerate(ns)}
    ex, ey = [], []
    for u, v in G.edges():
        if u in pos and v in pos: ex += [pos[u][0], pos[v][0], None]; ey += [pos[u][1], pos[v][1], None]
    fig = go.Figure(go.Scatter(x=ex, y=ey, mode="lines", line=dict(width=1, color="#cbd5e1"), hoverinfo="none"))
    ns = list(pos)
    fig.add_trace(go.Scatter(x=[pos[n][0] for n in ns], y=[pos[n][1] for n in ns], mode="markers+text",
                             text=[L.get(n, n) for n in ns], textposition="top center",
                             marker=dict(size=[34 if n == start else 22 for n in ns], color=[res[n][1] for n in ns],
                                         colorscale="Reds", cmin=0, cmax=1, showscale=True, colorbar=dict(title="Impact")),
                             hovertext=[f"{n} · impact {res[n][1]:.0%}" for n in ns], hoverinfo="text"))
    fig.update_layout(showlegend=False, height=520, margin=dict(l=10, r=10, t=20, b=10),
                      xaxis=dict(title="Cascade depth", dtick=1), yaxis=dict(visible=False))
    return fig

# ---------- Pages ----------
page = st.sidebar.radio("NAVIGATION", ["Dashboard", "Data Manager", "Timetable & Conflicts", "Incident Simulator", "Incident History"])
st.sidebar.caption("Data stored in omnisx.db (SQLite). Recommendations need human approval.")

if page == "Dashboard":
    tt = q(TT_SQL); cf = conflicts(tt)
    c = st.columns(5)
    c[0].metric("Students", int(q("select count(*) n from students")["n"][0]))
    c[1].metric("Faculty", int(q("select count(*) n from faculty")["n"][0]))
    c[2].metric("Rooms + Labs", int(q("select (select count(*) from classrooms)+(select count(*) from laboratories) n")["n"][0]))
    c[3].metric("Conflicts", len(cf))
    c[4].metric("Open incidents", int(q("select count(*) n from incidents where status='Open'")["n"][0]))
    l, r = st.columns([1.4, 1])
    with l:
        st.markdown("#### Timetable")
        show_df(tt[["subject", "faculty", "place", "day", "time"]])
    with r:
        st.markdown("#### Students per department")
        show_fig(px.bar(q("select d.department_name dept,count(s.student_id) students from departments d "
                          "left join students s on s.department_id=d.department_id group by 1"), x="dept", y="students"))
    if cf.empty: st.success("No conflicts detected.")
    else: st.warning(f"{len(cf)} issue(s) need attention."); show_df(cf)

elif page == "Data Manager":
    st.subheader("Database tables")
    t = st.selectbox("Table", TABLES)
    df = q(f"select * from {t}")
    ed = show_ed(df, num_rows="dynamic", key=f"ed_{t}")
    if st.button("Save changes", type="primary"):
        c = sqlite3.connect(DB)
        c.execute(f"delete from {t}"); ed.to_sql(t, c, if_exists="append", index=False)
        c.commit(); c.close(); st.success(f"{t} saved."); st.rerun()

elif page == "Timetable & Conflicts":
    st.subheader("Conflict detection")
    tt = q(TT_SQL); show_df(tt[["tid", "subject", "faculty", "place", "day", "time", "pstatus", "favail"]])
    cf = conflicts(tt)
    if cf.empty: st.success("No conflicts found.")
    else: st.error(f"{len(cf)} conflict(s) detected."); show_df(cf)
    st.caption("Mark a room 'Under Maintenance' or a faculty 'Absent' in Data Manager to see conflicts appear.")

elif page == "Incident Simulator":
    st.subheader("Cascading failure simulation & recovery")
    G, L = build_graph(), labels()
    nodes = [n for n in G.nodes if n.split(":")[0] in ("room", "lab", "faculty", "transport", "infra")]
    start = st.selectbox("Failed asset", nodes, format_func=lambda n: f'{n.split(":")[0].title()} · {L.get(n, n)}')
    thr = st.slider("Propagation threshold (lower = wider spread)", 0.1, 0.9, 0.3, 0.05)
    if st.button("Run simulation", type="primary"):
        res = cascade(G, start, thr)
        acts, changes, score = make_plan(start, res, L)
        st.session_state.sim = dict(start=start, res=res, acts=acts, changes=changes, score=score, saved=False)
    s = st.session_state.get("sim")
    if s:
        res, start = s["res"], s["start"]
        size = {int(a): int(b) for a, b in q("select department_id,count(*) from students group by 1").values}
        stu = round(sum(size.get(int(n.split(":")[1]), 0) * v[1] for n, v in res.items() if n.startswith("dept:")))
        kinds = {}
        for n in res: kinds[n.split(":")[0]] = kinds.get(n.split(":")[0], 0) + 1
        sev_score = sum(v[1] for n, v in res.items() if n != start)
        sev = "Critical" if sev_score >= 6 else "High" if sev_score >= 3 else "Medium" if sev_score >= 1.5 else "Low"
        m = st.columns(5)
        m[0].metric("Severity", sev); m[1].metric("Entities affected", len(res) - 1)
        m[2].metric("Classes affected", kinds.get("tt", 0)); m[3].metric("Students impacted (weighted)", stu)
        m[4].metric("Recovery score", f'{s["score"]}%')
        show_fig(plot_cascade(G, res, start, L))
        rows = [(d, n.split(":")[0].title(), L.get(n, n), f"{v:.0%}") for n, (d, v) in sorted(res.items(), key=lambda x: x[1])]
        st.markdown("#### Ripple effect"); show_df(pd.DataFrame(rows, columns=["Depth", "Type", "Entity", "Impact"]))
        st.markdown("#### Recovery plan")
        for a in s["acts"]: st.write(("⚠️ " if a.startswith("MANUAL") else "✅ ") + a)
        c1, c2 = st.columns(2)
        if c1.button("Save incident & plan", disabled=s["saved"]):
            summary = f"{sev}: {len(res)-1} entities, {kinds.get('tt', 0)} classes, ~{stu} students; kinds={kinds}"
            inc = run("insert into incidents(asset_id,severity,status) values(?,?,?)", (start, sev, "Open"))
            sim = run("insert into simulations(incident_id,impact_summary) values(?,?)", (inc, summary))
            plan = run("insert into recovery_plans(simulation_id,objective_score) values(?,?)", (sim, s["score"]))
            for a in s["acts"]: run("insert into recovery_actions(plan_id,action_description) values(?,?)", (plan, a))
            s["saved"] = True; st.success("Saved to database."); st.rerun()
        if c2.button("Apply timetable changes", disabled=not s["changes"]):
            for tid, col, new in s["changes"]: run(f"update timetables set {col}=? where timetable_id=?", (new, tid))
            st.session_state.sim = None; st.success("Timetable updated."); st.rerun()

elif page == "Incident History":
    st.subheader("Incidents, simulations and recovery plans")
    for t in ["incidents", "simulations", "recovery_plans", "recovery_actions"]:
        st.markdown(f"#### {t}"); d = q(f"select * from {t} order by 1 desc")
        show_df(d) if not d.empty else st.caption("No records yet.")
