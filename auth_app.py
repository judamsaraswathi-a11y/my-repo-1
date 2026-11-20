"""ZenTask AI-Powered Study Assistant - admin managed study materials."""
import os, uuid, json, shutil, hashlib
from pathlib import Path
from datetime import datetime, timezone
import streamlit as st
import bcrypt
from database import create_tables, connect_db, log_activity
from rag_utils import upload_pdf, ask_question, get_general_answer, get_uploaded_pdfs



def setup_cloud_admin():
    try:
        name = st.secrets["ZENTASK_ADMIN_NAME"]
        email = st.secrets["ZENTASK_ADMIN_EMAIL"].strip().lower()
        password = st.secrets["ZENTASK_ADMIN_PASSWORD"]
    except (KeyError, FileNotFoundError):
        return

    if not all((name, email, password)):
        return

    if len(password) < 12:
        raise ValueError("Admin password must be at least 12 characters.")

    conn = connect_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT
            )
        """)

        done = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key=?",
            ("cloud_admin_bootstrap_done",)
        ).fetchone()

        if done:
            return

        existing = conn.execute(
            "SELECT user_id FROM users WHERE lower(email)=?",
            (email,)
        ).fetchone()

        hashed = bcrypt.hashpw(
            password.encode(), bcrypt.gensalt()
        ).decode()

        if existing:
            conn.execute(
                """UPDATE users
                   SET name=?, password=?, role='Admin', is_active=1
                   WHERE user_id=?""",
                (name, hashed, existing["user_id"])
            )
            print("Cloud Admin account synchronized.")
        else:
            conn.execute(
                """INSERT INTO users
                   (name, email, password, role, created_at, is_active)
                   VALUES (?, ?, ?, 'Admin', datetime('now'), 1)""",
                (name, email, hashed)
            )
            print("Cloud Admin account created.")

        conn.execute(
            "INSERT INTO app_settings(setting_key, setting_value) VALUES (?, ?)",
            ("cloud_admin_bootstrap_done", "yes")
        )
        conn.commit()
    finally:
        conn.close()


st.set_page_config(page_title='ZenTask | AI Study Assistant',layout='wide')

# ZT_PROFESSIONAL_THEME
st.markdown(r'''
<style>
.stApp { background:#e8f2ef; color:#29413f; }
[data-testid="stSidebar"] {
    background:linear-gradient(180deg,#203f3d,#315b56);
}
[data-testid="stSidebar"] * { color:#f3f7f5 !important; }
.block-container { max-width:1500px; padding:2rem 3rem 4rem; }
h1,h2,h3 { color:#244743; font-weight:750; }
.zt-hero {
    background:linear-gradient(115deg,#294d49,#47736b);
    padding:30px 34px; border-radius:20px;
    color:white; margin-bottom:26px;
    box-shadow:0 9px 24px rgba(35,70,65,.16);
}
.zt-hero h2 { color:white !important; margin:0; font-size:30px; }
.zt-hero p { color:#e0ece8 !important; margin-top:8px; }
[data-testid="stMetric"] {
    background:white; border:1px solid #dce8e3;
    border-radius:16px; padding:20px;
    box-shadow:0 5px 16px rgba(38,72,66,.07);
}
[data-testid="stDataFrame"] {
    background:white; border-radius:14px;
}
.stButton > button {
    background:#315b55; color:white; border:0;
    border-radius:10px; font-weight:650;
}
.stButton > button:hover {
    background:#c5a34b; color:#203e3b; border:0;
}
.stTextInput input,.stTextArea textarea { border-radius:10px; }
div[data-testid="stAlert"] { border-radius:12px; }
hr { border-color:#d6e4df; }
</style>
''', unsafe_allow_html=True)

# ZT_LOGIN_PASTEL_STYLE

st.markdown('''
<style>
.stApp {background:linear-gradient(135deg,#e9ddff,#f7eefa 55%,#e9e0ff);}
.block-container {max-width:1250px;padding-top:1.2rem;}
h1,h2,h3 {color:#65418f;}
.stTextInput input {background:#fffaf7;border:1px solid #eadcf5;border-radius:18px;padding:14px;}
.stButton>button {background:linear-gradient(90deg,#9b69d1,#7950b4);color:white;border:0;border-radius:18px;padding:13px;font-weight:700;box-shadow:0 5px 14px #76509b35;}
.stButton>button:hover {background:#68449b;color:white;}
[data-testid="stTabs"] button {color:#68449b;font-weight:700;}
</style>
''', unsafe_allow_html=True)


# ZT_DASHBOARD_CARDS_V2
def zt_dashboard_cards(items):
    colors = ["#eee2ff", "#ffe5e4", "#fff0d4", "#e1eaff"]
    cards = []
    for i, item in enumerate(items):
        label, value, icon = item
        cards.append(
            f'<div style="background:{colors[i%4]};border-radius:18px;'
            f'padding:18px;box-shadow:0 5px 15px #73549b18;">'
            f'<div style="font-size:25px">{icon}</div>'
            f'<div style="color:#75658a;font-size:13px">{label}</div>'
            f'<div style="font-size:27px;font-weight:800;color:#392c53">{value}</div>'
            '</div>'
        )
    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:20px 0;">'
        + ''.join(cards) + '</div>',
        unsafe_allow_html=True
    )

def zt_dashboard_panel(title, description):
    st.markdown(
        f'<div style="background:#fffaf7;border-radius:18px;padding:20px;'
        f'margin:15px 0;border:1px solid #eee1f5;'
        f'box-shadow:0 5px 16px #73549b12;">'
        f'<b style="font-size:19px;color:#49345f">{title}</b>'
        f'<p style="color:#857694;margin-bottom:0">{description}</p></div>',
        unsafe_allow_html=True
    )

create_tables()
setup_cloud_admin()
UPLOAD_DIR=Path('uploads'); UPLOAD_DIR.mkdir(exist_ok=True)

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def get_classes():
    c=connect_db()
    try:return [dict(row) for row in c.execute('SELECT class_id,class_name FROM classes ORDER BY class_id').fetchall()]
    finally:c.close()
def get_subjects(cid):
    c=connect_db()
    try:return [dict(row) for row in c.execute('SELECT subject_id,subject_name FROM subjects WHERE class_id=? ORDER BY subject_name',(cid,)).fetchall()]
    finally:c.close()
def authenticate(email,password):
    c=connect_db()
    try:u=c.execute('SELECT user_id,name,password,role,class_id FROM users WHERE lower(email)=lower(?) AND is_active=1',(email.strip(),)).fetchone()
    finally:c.close()
    if not u:return None
    try:
        if bcrypt.checkpw(password.encode(),u['password'].encode()):return {'user_id':u['user_id'],'name':u['name'],'role':u['role'],'class_id':u['class_id']}
    except (ValueError,TypeError):pass
    return None
def register_student(name,email,password):
    if len(password)<8:return False,'Password must contain at least 8 characters.'
    hashed=bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()
    c=connect_db()
    try:
        c.execute('INSERT INTO users(name,email,password,role,created_at,is_active) VALUES(?,?,?,?,?,1)',(name.strip(),email.strip().lower(),hashed,'Student',now()));c.commit();return True,'Registration successful. Please log in.'
    except Exception as e:return False,('Email already registered.' if 'UNIQUE' in str(e).upper() else str(e))
    finally:c.close()

def register_parent(name, email, password, student_email):
    if len(password) < 8:
        return False, "Password must contain at least 8 characters."
    c = connect_db()
    try:
        student = c.execute(
            "SELECT user_id FROM users WHERE lower(email)=lower(?) AND lower(role)='student' AND is_active=1",
            (student_email.strip(),)
        ).fetchone()
        if not student:
            return False, "No active Student account found with that email."
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        c.execute(
            "INSERT INTO users(name,email,password,role,created_at,is_active) VALUES(?,?,?,?,?,1)",
            (name.strip(), email.strip().lower(), hashed, "Parent", now())
        )
        parent_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute(
            "INSERT INTO parent_student_links(parent_user_id,student_user_id,linked_at) VALUES(?,?,?)",
            (parent_id, student["user_id"], now())
        )
        c.commit()
        return True, "Parent account created and linked successfully. Please log in."
    except Exception as e:
        c.rollback()
        return False, "Email already registered." if "UNIQUE" in str(e).upper() else str(e)
    finally:
        c.close()

def log_event(user,kind,cid=None,sid=None,details=None):
    try:log_activity(user['user_id'],kind,cid,sid,details or {})
    except Exception:pass
def set_login(user):
    sid=str(uuid.uuid4()); c=connect_db()
    try:c.execute('INSERT INTO login_history(user_id,session_id,login_at,last_seen,status) VALUES(?,?,?,?,?)',(user['user_id'],sid,now(),now(),'active'));c.commit()
    finally:c.close()
    st.session_state.session_id=sid;st.session_state.login_at=now()
def logout():
    sid=st.session_state.get('session_id');u=st.session_state.get('user')
    if sid and u:
        c=connect_db()
        try:
            row=c.execute('SELECT login_at FROM login_history WHERE session_id=?',(sid,)).fetchone()
            duration=0
            if row:
                start=datetime.fromisoformat(row['login_at']);duration=max(0,int((datetime.now(timezone.utc)-start).total_seconds()))
            c.execute("UPDATE login_history SET logout_at=?,duration_seconds=?,status='closed' WHERE session_id=?",(now(),duration,sid));c.commit()
        finally:c.close()
        log_event(u,'logout')
    for k in ('user','session_id','login_at','selected_class','selected_subject'):st.session_state.pop(k,None)
    st.rerun()

if 'user' not in st.session_state:st.session_state.user=None

def maintain_sessions():
    c = connect_db()
    current_sid = st.session_state.get('session_id')
    expired_current = False
    current_time = datetime.now(timezone.utc)
    try:
        columns = {r['name'] for r in c.execute("PRAGMA table_info(login_history)").fetchall()}
        if 'last_seen' not in columns:
            c.execute("ALTER TABLE login_history ADD COLUMN last_seen TEXT")

        sessions = c.execute(
            "SELECT session_id, login_at, last_seen FROM login_history WHERE status='active'"
        ).fetchall()

        for row in sessions:
            seen = row['last_seen'] or row['login_at']
            try:
                age = (current_time - datetime.fromisoformat(seen)).total_seconds()
                if age > 1800:
                    start = datetime.fromisoformat(row['login_at'])
                    end = datetime.fromisoformat(seen)
                    duration = max(0, int((end - start).total_seconds()))
                    c.execute(
                        "UPDATE login_history SET logout_at=?, duration_seconds=?, status='abandoned' WHERE session_id=? AND status='active'",
                        (seen, duration, row['session_id'])
                    )
                    if row['session_id'] == current_sid:
                        expired_current = True
                elif row['session_id'] == current_sid:
                    c.execute(
                        "UPDATE login_history SET last_seen=? WHERE session_id=? AND status='active'",
                        (current_time.isoformat(timespec='seconds'), current_sid)
                    )
            except (ValueError, TypeError):
                continue
        c.commit()
    finally:
        c.close()

    if expired_current:
        for key in ('user', 'session_id', 'login_at', 'selected_class', 'selected_subject'):
            st.session_state.pop(key, None)
        st.session_state.user = None

maintain_sessions()

st.title('ZenTask')
st.caption('AI-Powered Study Assistant')


if st.session_state.user is None:
    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown(
            """<div style="text-align:center;padding:22px 8px 5px;">
            <h1 style="color:#68449b;">Welcome Back!</h1>
            <p style="color:#806d91;font-size:17px;">
            Login to continue your learning journey</p>
            </div>""",
            unsafe_allow_html=True
        )
        if Path("zentask_student.png").exists():
            st.image("zentask_student.png", width=440)

    with right:
        st.markdown(
            """<div style="background:linear-gradient(145deg,#fffaf5,#f5edff);
            border:1px solid #eadcf8;border-radius:28px;
            padding:24px 25px 18px;box-shadow:0 12px 35px #73549b20;">
            <h2 style="color:#68449b;text-align:center;">ZenTask</h2>
            <p style="color:#806d91;text-align:center;">
            AI-Powered Study Assistant</p>
            </div>""",
            unsafe_allow_html=True
        )

        login_tab, reg_tab, parent_tab = st.tabs(["Login", "Student Sign Up", "Parent Sign Up"])

        with login_tab:
            email = st.text_input("Email Address", key="login_email",
                                  placeholder="Enter your registered email")
            password = st.text_input("Password", type="password",
                                     key="login_password",
                                     placeholder="Enter your password")
            if st.button("Login", type="primary", use_container_width=True):
                user = authenticate(email, password)
                if user:
                    st.session_state.user = user
                    set_login(user)
                    log_event(user, "login")
                    st.rerun()
                else:
                    st.error("Invalid email or password, or account inactive.")

        with reg_tab:
            name = st.text_input("Full Name", key="reg_name")
            new_email = st.text_input("Email Address", key="reg_email")
            new_password = st.text_input(
                "Password (minimum 8 characters)",
                type="password", key="reg_password"
            )
            if st.button("Create Student Account", use_container_width=True):
                if not name.strip() or not new_email.strip() or not new_password:
                    st.warning("Fill all fields.")
                else:
                    ok, msg = register_student(name, new_email, new_password)
                    (st.success if ok else st.error)(msg)

        with parent_tab:
            st.subheader("Create Parent Account")
            parent_name = st.text_input("Parent Full Name", key="parent_name")
            parent_email = st.text_input("Parent Email Address", key="parent_email")
            parent_password = st.text_input("Parent Password (minimum 8 characters)", type="password", key="parent_password")
            student_email = st.text_input("Student Registered Email", key="parent_student_email")
            if st.button("Create Parent Account", use_container_width=True):
                if not all([parent_name.strip(), parent_email.strip(), parent_password, student_email.strip()]):
                    st.warning("Please fill all fields.")
                else:
                    ok, msg = register_parent(parent_name, parent_email, parent_password, student_email)
                    (st.success if ok else st.error)(msg)

        st.caption("Admin access is securely managed.")

else:
    user=st.session_state.user
    st.markdown(
        f"""<div class="zt-hero">
        <h2>Welcome back, {user['name']}</h2>
        <p>ZenTask | AI-Powered Study Assistant | Your learning workspace</p>
        </div>""",
        unsafe_allow_html=True
    )
    st.sidebar.write(f"Signed in: **{user['name']}**")
    if st.sidebar.button('Logout'):logout()
    if user['role'].lower()=='admin':
        page=st.sidebar.radio(
            'Admin Menu',
            ['Overview', 'Admin Profile', 'Student Management',
             'Manage Subjects', 'Upload Study PDFs',
             'Admin Activity', 'Student Activity']
        )
        if page == 'Admin Profile':
            st.header('Admin Profile')
            st.caption('View and update your account details.')
            profile_conn = connect_db()
            try:
                profile = profile_conn.execute(
                    'SELECT name, email, role FROM users WHERE user_id=?',
                    (user['user_id'],)
                ).fetchone()
            finally:
                profile_conn.close()

            if profile:
                st.write(f"**Account role:** {profile['role']}")
                with st.form('admin_profile_form'):
                    updated_name = st.text_input('Full name', value=profile['name'])
                    updated_email = st.text_input('Email address', value=profile['email'])
                    save_profile = st.form_submit_button('Save profile')
                if save_profile:
                    if not updated_name.strip() or not updated_email.strip():
                        st.error('Name and email are required.')
                    else:
                        profile_conn = connect_db()
                        try:
                            profile_conn.execute(
                                'UPDATE users SET name=?, email=? WHERE user_id=?',
                                (updated_name.strip(), updated_email.strip().lower(),
                                 user['user_id'])
                            )
                            profile_conn.commit()
                            st.session_state.user['name'] = updated_name.strip()
                            st.success('Profile updated successfully.')
                            st.rerun()
                        except Exception:
                            st.error('Could not update profile. The email may already be in use.')
                        finally:
                            profile_conn.close()

                st.divider()
                st.subheader('Change password')
                with st.form('admin_password_form'):
                    current_password = st.text_input('Current password', type='password')
                    new_password = st.text_input('New password (minimum 12 characters)', type='password')
                    confirm_password = st.text_input('Confirm new password', type='password')
                    change_password = st.form_submit_button('Update password')
                if change_password:
                    if not current_password or not new_password or not confirm_password:
                        st.error('Complete all password fields.')
                    elif len(new_password) < 12:
                        st.error('New password must contain at least 12 characters.')
                    elif new_password != confirm_password:
                        st.error('New passwords do not match.')
                    else:
                        password_conn = connect_db()
                        try:
                            stored = password_conn.execute(
                                'SELECT password FROM users WHERE user_id=?',
                                (user['user_id'],)
                            ).fetchone()
                            if not stored or not bcrypt.checkpw(
                                current_password.encode(), stored['password'].encode()
                            ):
                                st.error('Current password is incorrect.')
                            else:
                                new_hash = bcrypt.hashpw(
                                    new_password.encode(), bcrypt.gensalt()
                                ).decode()
                                password_conn.execute(
                                    'UPDATE users SET password=? WHERE user_id=?',
                                    (new_hash, user['user_id'])
                                )
                                password_conn.commit()
                                st.success('Password changed successfully.')
                        finally:
                            password_conn.close()

        elif page == 'Student Management':
            st.header('Student Management')
            st.caption('View registered student accounts.')
            students_conn = connect_db()
            try:
                student_rows = students_conn.execute(
                    """SELECT user_id, name, email, created_at, is_active
                       FROM users WHERE lower(role)='student'
                       ORDER BY user_id DESC"""
                ).fetchall()
            finally:
                students_conn.close()
            if student_rows:
                st.dataframe(
                    [{
                        'Student ID': row['user_id'],
                        'Name': row['name'],
                        'Email': row['email'],
                        'Registered': row['created_at'] or '—',
                        'Status': 'Active' if row['is_active'] else 'Inactive'
                    } for row in student_rows],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info('No student accounts are registered in this database yet.')

        elif page=='Overview':
            c=connect_db()
            try:
                students=c.execute(
    "SELECT COUNT(*) n FROM users WHERE lower(role)='student' AND is_active=1"
).fetchone()['n']
                materials=c.execute("SELECT COUNT(*) n FROM study_materials WHERE is_active=1 AND visibility='shared'").fetchone()['n']
                active=c.execute("SELECT COUNT(*) n FROM login_history WHERE status='active'").fetchone()['n']
            finally:c.close()
            login_conn = connect_db()
            try:
                total_logins = login_conn.execute("SELECT COUNT(*) n FROM login_history").fetchone()['n']
            finally:
                login_conn.close()
            zt_dashboard_cards([
                ('Active Students', students, '🎓'),
                ('Shared PDFs', materials, '📚'),
                ('Active Sessions', active, '🟣'),
                ('Total Logins', total_logins, '📈')
            ])
            zt_dashboard_panel('Admin Learning Workspace', 'Manage students, subjects, PDFs and learning activity.')
            st.subheader('Available Classes')
            st.dataframe([dict(class_name=x['class_name']) for x in get_classes()],use_container_width=True)
        elif page=='Manage Subjects':
            classes=get_classes();selected=st.selectbox('Select Class',classes,format_func=lambda x:x['class_name'])
            subject=st.text_input('Subject name (add only subjects you have selected)')
            if st.button('Add Subject'):
                if not subject.strip():st.warning('Enter subject name.')
                else:
                    c=connect_db()
                    try:
                        exists=c.execute('SELECT 1 FROM subjects WHERE class_id=? AND lower(subject_name)=lower(?)',(selected['class_id'],subject.strip())).fetchone()
                        if exists:st.warning('Subject already exists.')
                        else:c.execute('INSERT INTO subjects(subject_name,class_id) VALUES(?,?)',(subject.strip(),selected['class_id']));c.commit();st.success('Subject added.')
                    finally:c.close()
            st.subheader('Subjects already configured')
            st.dataframe([dict(subject=x['subject_name']) for x in get_subjects(selected['class_id'])],use_container_width=True)
            st.caption('For classes 6th–8th, add Biology, Chemistry and Physics under General Science only if those are the subjects you want enabled.')
        elif page=='Upload Study PDFs':
            classes=get_classes();cl=st.selectbox('Class',classes,format_func=lambda x:x['class_name'],key='admin_class')
            subs=get_subjects(cl['class_id'])
            if not subs:st.warning('No subjects configured for this class. Add a subject first.')
            else:
                su=st.selectbox('Subject',subs,format_func=lambda x:x['subject_name'],key='admin_subject')
                kind=st.selectbox('PDF Type',[('Textbook PDF','textbook'),('Answer PDF','answer')],format_func=lambda x:x[0])[1]
                pdf=st.file_uploader('Choose PDF',type=['pdf'],key='admin_pdf')
                if pdf and st.button('Upload and Process PDF',type='primary'):
                    if pdf.size>30*1024*1024:st.error('PDF size must be 30 MB or less.')
                    else:
                        data=pdf.getvalue();result=upload_pdf(data,pdf.name,uploader=user['name'],class_id=cl['class_id'],subject_id=su['subject_id'],material_type=kind)
                        if result['status']=='success':
                            safe_name=f"{result['file_hash']}_{Path(pdf.name).name}";path=UPLOAD_DIR/safe_name
                            path.write_bytes(data)
                            c=connect_db()
                            try:
                                c.execute("INSERT INTO study_materials(title,file_path,subject_id,uploaded_by,material_type,visibility,file_hash,uploaded_at,is_active) VALUES(?,?,?,?,?,'shared',?,?,1)",(Path(pdf.name).name,str(path),su['subject_id'],user['user_id'],kind,result['file_hash'],now()));c.commit()
                            finally:c.close()
                            log_event(user,'admin_pdf_upload',cl['class_id'],su['subject_id'],{'filename':pdf.name,'type':kind});st.success(result['message']+f" Pages: {result['pages']}, chunks: {result['chunks']}")
                        elif result['status']=='duplicate':st.info(result['message'])
                        else:st.error(result['message'])
            st.subheader('Shared PDFs')
            c=connect_db()
            try:rows=c.execute("SELECT m.material_id,m.title,m.file_path,m.material_type,m.uploaded_at,s.subject_name,cl.class_name FROM study_materials m JOIN subjects s ON s.subject_id=m.subject_id JOIN classes cl ON cl.class_id=s.class_id WHERE m.is_active=1 AND m.visibility='shared' ORDER BY m.uploaded_at DESC").fetchall()
            finally:c.close()
            if rows:
                pdf_options = [dict(row) for row in rows]
                selected_pdf = st.selectbox(
                    'Select PDF to view or download',
                    pdf_options,
                    format_func=lambda x: f"{x['title']} | {x['material_type'].title()} | {x['subject_name']}"
                )
                pdf_path = Path(selected_pdf['file_path'])

                if pdf_path.is_file():
                    pdf_bytes = pdf_path.read_bytes()
                    st.download_button(
                        'Download PDF',
                        data=pdf_bytes,
                        file_name=selected_pdf['title'],
                        mime='application/pdf',
                        key=f"download_pdf_{selected_pdf['material_id']}"
                    )
                    st.subheader('PDF Preview')
                    st.pdf(pdf_bytes)
                else:
                    st.error('PDF file is missing from storage.')
            else:
                st.info('No shared PDFs available.')
        elif page in ('Admin Activity', 'Student Activity'):
            st.header(page)
            st.caption('Login and logout history in Indian Standard Time (IST).')
            role_filter = 'admin' if page == 'Admin Activity' else 'student'
            c = connect_db()
            try:
                rows = c.execute(
                    """SELECT u.name, u.email, u.role, lh.login_at,
                              lh.logout_at, lh.duration_seconds, lh.status
                       FROM login_history lh
                       JOIN users u ON u.user_id = lh.user_id
                       WHERE lower(u.role) = ?
                       ORDER BY lh.login_id DESC LIMIT 500""",
                    (role_filter,)
                ).fetchall()
            finally:
                c.close()

            from datetime import timedelta
            ist = timezone(timedelta(hours=5, minutes=30))

            def show_ist(value):
                if not value:
                    return 'Not logged out'
                try:
                    dt = datetime.fromisoformat(value)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(ist).strftime('%d-%m-%Y %I:%M:%S %p')
                except (ValueError, TypeError):
                    return str(value)

            activity = []
            for item in rows:
                r = dict(item)
                seconds = r['duration_seconds']
                r['Login Date & Time (IST)'] = show_ist(r.pop('login_at'))
                r['Logout Date & Time (IST)'] = show_ist(r.pop('logout_at'))
                r['Session Duration'] = (
                    f"{seconds // 3600}h {(seconds % 3600) // 60}m"
                    if seconds is not None else 'In progress'
                )
                r.pop('duration_seconds', None)
                activity.append(r)

            if activity:
                st.dataframe(activity, use_container_width=True, hide_index=True)
            else:
                st.info('No activity recorded yet for this account type.')
    elif user['role'].lower() == 'parent':
        st.header("Parent Dashboard")
        st.caption("Monitor your linked student's learning activity.")

        pc = connect_db()
        try:
            linked = pc.execute(
                """SELECT u.user_id, u.name, u.email
                   FROM parent_student_links l
                   JOIN users u ON u.user_id=l.student_user_id
                   WHERE l.parent_user_id=? AND lower(u.role)='student' AND u.is_active=1""",
                (user['user_id'],)
            ).fetchone()

            if linked:
                student_id = linked['user_id']
                st.subheader(f"Student: {linked['name']}")
                st.caption(f"Student email: {linked['email']}")

                ai_questions = pc.execute(
                    "SELECT activity_type, details_json, created_at FROM activity_logs WHERE user_id=? AND activity_type='ai_question' ORDER BY activity_id DESC LIMIT 50",
                    (student_id,)
                ).fetchall()

                pdf_activity = pc.execute(
                    "SELECT details_json, created_at FROM activity_logs WHERE user_id=? AND activity_type='pdf_open' ORDER BY activity_id DESC LIMIT 50",
                    (student_id,)
                ).fetchall()

                quizzes = pc.execute(
                    """SELECT quiz_title, score, total_questions, started_at, completed_at
                       FROM quiz_attempts WHERE user_id=?
                       ORDER BY attempt_id DESC LIMIT 50""",
                    (student_id,)
                ).fetchall()

                sessions = pc.execute(
                    """SELECT login_at, logout_at, duration_seconds, status
                       FROM login_history WHERE user_id=?
                       ORDER BY login_id DESC LIMIT 50""",
                    (student_id,)
                ).fetchall()

                progress = pc.execute(
                    """SELECT cl.class_name, su.subject_name, lp.last_chapter,
                              lp.last_page, lp.progress_percent, lp.updated_at
                       FROM learning_progress lp
                       LEFT JOIN classes cl ON cl.class_id=lp.class_id
                       LEFT JOIN subjects su ON su.subject_id=lp.subject_id
                       WHERE lp.user_id=? ORDER BY lp.updated_at DESC""",
                    (student_id,)
                ).fetchall()

                st.divider()
                st.subheader("Student Overview")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("AI Questions", len(ai_questions))
                m2.metric("PDF Opens", len(pdf_activity))
                m3.metric("Quiz Attempts", len(quizzes))
                m4.metric("Login Sessions", len(sessions))

                st.divider()
                st.subheader("Learning Progress")
                if progress:
                    st.dataframe([dict(x) for x in progress], use_container_width=True, hide_index=True)
                else:
                    st.info("No learning progress recorded yet.")

                st.subheader("AI Questions")
                if ai_questions:
                    st.dataframe(
                        [{"Question Details": x['details_json'], "Date & Time (UTC)": x['created_at']} for x in ai_questions],
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("No AI questions recorded yet.")

                st.subheader("PDF Activity")
                if pdf_activity:
                    st.dataframe(
                        [{"PDF Details": x['details_json'], "Date & Time (UTC)": x['created_at']} for x in pdf_activity],
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("No PDF opening activity recorded yet.")

                st.subheader("Quiz Scores")
                if quizzes:
                    st.dataframe([dict(x) for x in quizzes], use_container_width=True, hide_index=True)
                else:
                    st.info("No quiz attempts recorded yet.")

                st.subheader("Login History")
                if sessions:
                    session_rows = []
                    for item in sessions:
                        seconds = item['duration_seconds']
                        session_rows.append({
                            "Login Time (UTC)": item['login_at'],
                            "Logout Time (UTC)": item['logout_at'] or "Not logged out",
                            "Duration": f"{seconds // 3600}h {(seconds % 3600) // 60}m" if seconds is not None else "In progress",
                            "Status": item['status']
                        })
                    st.dataframe(session_rows, use_container_width=True, hide_index=True)
                else:
                    st.info("No login history recorded yet.")
            else:
                st.warning("No active student is linked to this Parent account.")
        finally:
            pc.close()

    elif user['role'].lower()=='student':
        st.markdown(
            f'<div style="background:linear-gradient(110deg,#a989df,#7655b2);'
            f'border-radius:22px;padding:25px;color:white;margin-bottom:18px;">'
            f'<div style="font-size:27px;font-weight:800;color:white;">Welcome back, {user["name"]}!</div>'
            f'<div style="color:#f5edff;">Your AI-powered learning space is ready.</div></div>',
            unsafe_allow_html=True
        )
        student_conn = connect_db()
        try:
            material_count = student_conn.execute(
                "SELECT COUNT(*) n FROM study_materials WHERE visibility='shared' AND is_active=1"
            ).fetchone()['n']
            chat_count = student_conn.execute(
                "SELECT COUNT(*) n FROM chat_sessions WHERE user_id=?",
                (user['user_id'],)
            ).fetchone()['n']
            question_count = student_conn.execute(
                "SELECT COUNT(*) n FROM activity_logs WHERE user_id=? AND activity_type='ai_question'",
                (user['user_id'],)
            ).fetchone()['n']
        finally:
            student_conn.close()
        zt_dashboard_cards([
            ('Shared Study PDFs', material_count, '📚'),
            ('Study Sessions', chat_count, '📖'),
            ('AI Questions', question_count, '💡'),
            ('Study Assistant', 'Ready', '🎓')
        ])
        zt_dashboard_panel('Your Learning Workspace', 'Choose your class and subject to explore PDFs and ask your AI Study Assistant.')
        classes=get_classes()
        if not classes:st.warning('No classes configured. Contact Admin.')
        else:
            previous=st.session_state.get('selected_class')
            idx=next((i for i,x in enumerate(classes) if previous and x['class_id']==previous),0)
            cl=st.selectbox('Choose Class',classes,index=idx,format_func=lambda x:x['class_name'])
            st.session_state.selected_class=cl['class_id']
            subs=get_subjects(cl['class_id'])
            if not subs:st.info('No subjects configured for this class yet.')
            else:
                prevs=st.session_state.get('selected_subject');sidx=next((i for i,x in enumerate(subs) if prevs and x['subject_id']==prevs),0)
                su=st.selectbox('Choose Subject',subs,index=sidx,format_func=lambda x:x['subject_name'])
                st.session_state.selected_subject=su['subject_id'];cid=cl['class_id'];sid=su['subject_id']
                log_event(user,'class_subject_selected',cid,sid)
                st.subheader('Study Materials')
                c=connect_db()
                try:materials=c.execute("SELECT m.material_id,m.title,m.file_path,m.material_type FROM study_materials m JOIN users up ON up.user_id=m.uploaded_by WHERE m.subject_id=? AND m.visibility='shared' AND m.is_active=1 AND lower(up.role)='admin' ORDER BY m.material_type,m.title",(sid,)).fetchall()
                finally:c.close()
                if materials:
                    for m in materials:
                        left,right=st.columns([4,1]);left.write(f"**{m['title']}** — {m['material_type'].title()} PDF")
                        p=Path(m['file_path'])
                        if p.exists():right.download_button('Download',p.read_bytes(),file_name=m['title'],mime='application/pdf',key=f"download_{m['material_id']}")
                        else:right.caption('File unavailable')
                        if st.button('Record as opened',key=f"opened_{m['material_id']}"):
                            log_event(user,'pdf_open',cid,sid,{'material_id':m['material_id'],'title':m['title']});st.success('Activity recorded.')
                else:st.info('No shared PDFs for this class and subject yet.')
                st.divider();st.subheader('AI Study Chat')
                question=st.text_area('Ask a question from your selected subject',key=f'question_{cid}_{sid}')
                if st.button('Search PDFs and Get AI Answer',type='primary'):
                    if not question.strip():st.warning('Enter a question.')
                    else:
                        try:
                            answer=ask_question(question,cid,sid)
                            st.session_state.last_answer=answer;st.session_state.last_question=question
                            log_event(user,'ai_question',cid,sid,{'question':question[:500]})
                            c=connect_db()
                            try:
                                c.execute("INSERT INTO chat_sessions(user_id,class_id,subject_id,title,created_at,updated_at) VALUES(?,?,?,?,?,?)",(user['user_id'],cid,sid,question[:80],now(),now()));chatid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                                c.execute("INSERT INTO chat_messages(chat_session_id,user_id,role,message,source_type,created_at) VALUES(?,?,?,?,?,?)",(chatid,user['user_id'],'user',question,'pdf_search',now()))
                                c.execute("INSERT INTO chat_messages(chat_session_id,user_id,role,message,source_type,created_at) VALUES(?,?,?,?,?,?)",(chatid,user['user_id'],'assistant',answer,'pdf_search',now()));c.commit()
                            finally:c.close()
                        except Exception as e:st.error(f'Unable to answer: {e}')
                if st.session_state.get('last_answer'):st.markdown(st.session_state.last_answer)
                if st.button('Get Separate General AI Answer'):
                    q=st.session_state.get('last_question') or question
                    if not q.strip():st.warning('Ask a question first.')
                    else:
                        try:st.markdown('**General knowledge answer (not from the uploaded PDFs)**');st.markdown(get_general_answer(q));log_event(user,'general_ai_answer',cid,sid)
                        except Exception as e:st.error(str(e))
                st.subheader('Recent Chat History')
                c=connect_db()
                try:history=c.execute("SELECT role,message,created_at FROM chat_messages WHERE user_id=? ORDER BY message_id DESC LIMIT 10",(user['user_id'],)).fetchall()
                finally:c.close()
                for item in reversed(history):st.caption(f"{item['created_at']} · {item['role']}");st.write(item['message'])
    else:
        st.info('This account role is not enabled in this release. Contact Admin.')
