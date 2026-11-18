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
        existing = conn.execute(
            "SELECT user_id, role FROM users WHERE lower(email)=?",
            (email,)
        ).fetchone()

        if existing:
            if existing["role"].lower() != "admin":
                hashed = bcrypt.hashpw(
                    password.encode(), bcrypt.gensalt()
                ).decode()
                conn.execute(
                    """UPDATE users
                       SET name=?, password=?, role='Admin', is_active=1
                       WHERE user_id=?""",
                    (name, hashed, existing["user_id"])
                )
                conn.commit()
                print("Existing account promoted to Admin.")
        else:
            hashed = bcrypt.hashpw(
                password.encode(), bcrypt.gensalt()
            ).decode()
            conn.execute(
                """INSERT INTO users
                   (name, email, password, role, created_at, is_active)
                   VALUES (?, ?, ?, 'Admin', datetime('now'), 1)""",
                (name, email, hashed)
            )
            conn.commit()
            print("Cloud Admin account created.")
    finally:
        conn.close()


st.set_page_config(page_title='ZenTask | AI Study Assistant',layout='wide')
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
def log_event(user,kind,cid=None,sid=None,details=None):
    try:log_activity(user['user_id'],kind,cid,sid,details or {})
    except Exception:pass
def set_login(user):
    sid=str(uuid.uuid4()); c=connect_db()
    try:c.execute('INSERT INTO login_history(user_id,session_id,login_at,status) VALUES(?,?,?,?)',(user['user_id'],sid,now(),'active'));c.commit()
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
st.title('ZenTask')
st.caption('AI-Powered Study Assistant')
if st.session_state.user is None:
    login_tab,reg_tab=st.tabs(['Login','Student Registration'])
    with login_tab:
        email=st.text_input('Email',key='login_email');password=st.text_input('Password',type='password',key='login_password')
        if st.button('Login',type='primary'):
            user=authenticate(email,password)
            if user:
                st.session_state.user=user;set_login(user);log_event(user,'login');st.rerun()
            else:st.error('Invalid email or password, or account inactive.')
    with reg_tab:
        name=st.text_input('Full Name',key='reg_name');new_email=st.text_input('Email',key='reg_email');new_password=st.text_input('Password (minimum 8 characters)',type='password',key='reg_password')
        if st.button('Create Student Account'):
            if not name.strip() or not new_email.strip() or not new_password:st.warning('Fill all fields.')
            else:
                ok,msg=register_student(name,new_email,new_password)
                (st.success if ok else st.error)(msg)
    st.info('Admin accounts are created only through the secure create_admin.py setup script. Public Admin registration is disabled.')
else:
    user=st.session_state.user
    st.sidebar.write(f"Signed in: **{user['name']}**")
    if st.sidebar.button('Logout'):logout()
    if user['role'].lower()=='admin':
        page=st.sidebar.radio(
            'Admin Menu',
            ['Overview', 'Admin Profile', 'Student Management',
             'Manage Subjects', 'Upload Study PDFs', 'Student Activity']
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
            a,b,d=st.columns(3);a.metric('Active student accounts',students);b.metric('Shared PDFs',materials);d.metric('Active sessions',active)
            st.write('Classes available');st.dataframe([dict(class_name=x['class_name']) for x in get_classes()],use_container_width=True)
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
            try:rows=c.execute("SELECT m.title,m.material_type,m.uploaded_at,s.subject_name,cl.class_name FROM study_materials m JOIN subjects s ON s.subject_id=m.subject_id JOIN classes cl ON cl.class_id=s.class_id WHERE m.is_active=1 AND m.visibility='shared' ORDER BY m.uploaded_at DESC").fetchall()
            finally:c.close()
            st.dataframe([dict(x) for x in rows],use_container_width=True)
        else:
            c=connect_db()
            try:rows=c.execute("SELECT u.name,u.email,lh.login_at,lh.logout_at,lh.duration_seconds,lh.status FROM login_history lh JOIN users u ON u.user_id=lh.user_id ORDER BY lh.login_id DESC LIMIT 300").fetchall()
            finally:c.close()
            st.dataframe([dict(x) for x in rows],use_container_width=True)
    elif user['role'].lower()=='student':
        st.header(f"Welcome, {user['name']}")
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
