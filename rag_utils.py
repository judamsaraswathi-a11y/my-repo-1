"""ZenTask RAG utilities. Legacy vectors are retained but never exposed to students."""
from __future__ import annotations
import hashlib, io, json, math, os, sqlite3, time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pypdf import PdfReader
load_dotenv()
VECTOR_DB_PATH=Path(os.getenv("VECTOR_DB_PATH","./study_vectors.db"))
EMBEDDING_MODEL=os.getenv("GEMINI_EMBEDDING_MODEL","gemini-embedding-001")
GENERATION_MODEL=os.getenv("GEMINI_MODEL","gemini-3.5-flash-lite")
CHUNK_SIZE=1200; CHUNK_OVERLAP=150; EMBEDDING_BATCH_SIZE=8; MAX_API_ATTEMPTS=5
_client=None

def _connect():
    VECTOR_DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(VECTOR_DB_PATH),timeout=30); c.row_factory=sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000"); c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE IF NOT EXISTS vectors (id TEXT PRIMARY KEY, document TEXT NOT NULL, embedding TEXT NOT NULL, metadata TEXT NOT NULL)")
    c.commit(); return c

def get_gemini_client():
    global _client
    if _client is None:
        key=os.getenv('GEMINI_API_KEY')
        if not key: raise RuntimeError('GEMINI_API_KEY missing. Check .env file.')
        _client=genai.Client(api_key=key)
    return _client

def split_text(text,chunk_size=CHUNK_SIZE,overlap=CHUNK_OVERLAP):
    text=' '.join((text or '').split())
    if not text:return []
    if chunk_size<=0 or overlap<0 or overlap>=chunk_size: raise ValueError('Invalid chunk settings')
    result=[]; start=0
    while start<len(text):
        end=min(start+chunk_size,len(text)); part=text[start:end].strip()
        if part: result.append(part)
        if end>=len(text):break
        start=end-overlap
    return result

def _retry(fn,label):
    for attempt in range(1,MAX_API_ATTEMPTS+1):
        try:return fn()
        except Exception as e:
            msg=str(e).lower()
            if not any(x in msg for x in ('429','500','502','503','504','unavailable','timeout','resource_exhausted')) or attempt==MAX_API_ATTEMPTS: raise
            time.sleep(min(2**(attempt-1),20))

def embed_texts(texts,task_type='RETRIEVAL_DOCUMENT'):
    if not texts:return []
    client=get_gemini_client(); output=[]
    for start in range(0,len(texts),EMBEDDING_BATCH_SIZE):
        batch=texts[start:start+EMBEDDING_BATCH_SIZE]
        response=_retry(lambda:client.models.embed_content(model=EMBEDDING_MODEL,contents=batch,config=types.EmbedContentConfig(task_type=task_type)), 'Gemini embedding')
        if not getattr(response,'embeddings',None): raise RuntimeError('Gemini returned no embeddings')
        output.extend([[float(v) for v in item.values] for item in response.embeddings])
    if len(output)!=len(texts):raise RuntimeError('Embedding count mismatch')
    return output

def upload_pdf(pdf_bytes,filename,uploader=None,class_id=None,subject_id=None,material_type='textbook'):
    if not pdf_bytes:return {'status':'error','message':'PDF is empty.'}
    if not class_id or not subject_id:return {'status':'error','message':'Class and subject are required.'}
    if material_type not in ('textbook','answer'):return {'status':'error','message':'Invalid PDF type.'}
    try:
        digest=hashlib.sha256(pdf_bytes).hexdigest(); conn=_connect()
        try:
            rows=conn.execute('SELECT metadata FROM vectors').fetchall()
            for row in rows:
                m=json.loads(row['metadata'] or '{}')
                if m.get('file_hash')==digest and m.get('class_id')==int(class_id) and m.get('subject_id')==int(subject_id) and m.get('material_type')==material_type and m.get('admin_approved') is True:
                    return {'status':'duplicate','message':f'{filename} already uploaded for this class and subject.'}
        finally:conn.close()
        reader=PdfReader(io.BytesIO(pdf_bytes)); chunks=[]
        for page_no,page in enumerate(reader.pages,1):
            chunks.extend((part,page_no) for part in split_text(page.extract_text() or ''))
        if not chunks:return {'status':'error','message':'No selectable text found. Scanned PDF needs OCR.'}
        texts=[x[0] for x in chunks]; vectors=embed_texts(texts)
        ids=[]; metadata=[]
        for i,(_,page) in enumerate(chunks):
            ids.append(hashlib.sha256(f'{digest}:{class_id}:{subject_id}:{material_type}:{i}'.encode()).hexdigest())
            metadata.append({'filename':Path(filename).name,'chapter':Path(filename).stem,'chapter_name':Path(filename).stem,'page':page,'page_number':page,'chunk':i,'chunk_index':i,'file_hash':digest,'uploader':str(uploader or 'admin'),'uploaded_by':str(uploader or 'admin'),'class_id':int(class_id),'subject_id':int(subject_id),'material_type':material_type,'visibility':'shared','admin_approved':True})
        conn=_connect()
        try:
            conn.executemany('INSERT OR REPLACE INTO vectors(id,document,embedding,metadata) VALUES(?,?,?,?)',[(i,t,json.dumps(v,separators=(',',':')),json.dumps(m,ensure_ascii=False)) for i,t,v,m in zip(ids,texts,vectors,metadata)])
            conn.commit()
        finally:conn.close()
        return {'status':'success','message':f'{filename} processed.','filename':Path(filename).name,'pages':len(reader.pages),'chunks':len(ids),'file_hash':digest}
    except Exception as e:return {'status':'error','message':str(e)}

def _matches(m, class_id, subject_id, material_type=None):
    return (m.get('admin_approved') is True and m.get('visibility')=='shared' and m.get('class_id')==int(class_id) and m.get('subject_id')==int(subject_id) and (material_type is None or m.get('material_type')==material_type))

def get_uploaded_pdfs(class_id,subject_id):
    c=_connect()
    try:rows=c.execute('SELECT metadata FROM vectors').fetchall()
    finally:c.close()
    found={}
    for row in rows:
        m=json.loads(row['metadata'] or '{}')
        if _matches(m,class_id,subject_id):
            key=(m.get('file_hash'),m.get('material_type'))
            found.setdefault(key,{'filename':m.get('filename'),'material_type':m.get('material_type'),'pages':set()})['pages'].add(m.get('page'))
    return [{'filename':v['filename'],'material_type':v['material_type'],'pages':len(v['pages'])} for v in found.values()]

def ask_question(question,class_id,subject_id,n_results=5,material_type=None):
    question=(question or '').strip()
    if not question:return 'Please enter a question.'
    if not class_id or not subject_id:return 'Select a class and subject first.'
    qv=embed_texts([question],task_type='RETRIEVAL_QUERY')[0]
    c=_connect()
    try:rows=c.execute('SELECT document,embedding,metadata FROM vectors').fetchall()
    finally:c.close()
    scored=[]; qnorm=math.sqrt(sum(x*x for x in qv))
    for row in rows:
        m=json.loads(row['metadata'] or '{}')
        if not _matches(m,class_id,subject_id,material_type):continue
        v=json.loads(row['embedding']); norm=math.sqrt(sum(x*x for x in v))
        if norm and len(v)==len(qv):scored.append((1-sum(a*b for a,b in zip(qv,v))/(qnorm*norm),row['document'],m))
    scored.sort(key=lambda x:x[0]); chosen=scored[:n_results]
    context="\n\n---\n\n".join(f"Source: {m.get('filename')}, page: {m.get('page')}, type: {m.get('material_type')}\n{text}" for _,text,m in chosen)
    prompt=f"""You are ZenTask, an AI study assistant. Answer in simple language and in the same language as the student. Use only the selected class/subject study-material context as PDF evidence. If it does not contain the answer, clearly label the explanation as General knowledge. Never claim a general-knowledge fact came from a PDF. Include source filename and page when context is used.\n\nSELECTED MATERIAL:\n{context or 'No matching approved PDF chunks found.'}\n\nQUESTION:\n{question}\n\nANSWER:"""
    response=_retry(lambda:get_gemini_client().models.generate_content(model=GENERATION_MODEL,contents=prompt),'Gemini answer')
    return (getattr(response,'text',None) or 'AI did not return a text answer. Please try again.').strip()

def get_general_answer(question):
    prompt = "Explain this for a school student in simple language. Label it General knowledge. Do not claim it came from a textbook.\nQuestion: " + question
    response=_retry(lambda:get_gemini_client().models.generate_content(model=GENERATION_MODEL,contents=prompt),'Gemini general answer')
    return (getattr(response,'text',None) or 'AI did not return a text answer.').strip()
