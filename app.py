import streamlit as st
from kbo.config import Config
from kbo.store import Store
from kbo.data import items
from kbo.collect import Collector
from kbo.rag import RAG,discover
st.set_page_config(page_title='KBO INSIDE',page_icon='⚾',layout='wide')
st.markdown("""<style>
.stApp{background:#0b1220;color:#eef3fa}h1{letter-spacing:-1.5px}.stButton button{border-radius:12px}
[data-testid="stSidebar"]{background:#121d30}.hero{padding:28px;border:1px solid #33415b;border-radius:20px;background:linear-gradient(120deg,#182840,#142032);margin-bottom:20px}.tag{color:#a6ed77;font-weight:700;letter-spacing:3px}
</style><div class="hero"><div class="tag">BASEBALL, WITH EVIDENCE</div><h1>⚾ KBO INSIDE</h1><p>구단의 한 시즌을 고르고, 기록을 근거와 함께 읽으세요.</p></div>""",unsafe_allow_html=True)
cfg=Config()
if cfg.mode=='online' and not cfg.key:
    st.error('API 키가 없습니다. .env에서 OPENAI_API_KEY를 설정하세요.');st.stop()
@st.cache_resource
def setup(mode,model):return Store(Config())
store=setup(cfg.mode,cfg.embed_model);rag=RAG(store);all_items=items()
if cfg.mode=='demo':st.info('데모 모드 · API 키 없이 실행됩니다. 로컬 해시 벡터와 정해진 발췌 답변을 사용합니다. 온라인 LLM·의미 검색과 구분하세요.')
with st.sidebar:
    st.header('DUGOUT / 시즌 선택')
    st.caption('기록 범위: 2015–2024 · 실시간 데이터 아님')
    st.metric('시즌 메타데이터',store.meta.count())
    st.metric('문서 청크',store.docs.count())
    if st.button('100개 시즌 데이터 색인',use_container_width=True):
        try:
            with st.status('데이터와 문서 색인 중…',expanded=True) as status:
                store.index_items(all_items)
                collector=Collector(cfg,store)
                for it in all_items:collector.collect(it,'',online=False)
                status.update(label='색인 완료',state='complete')
            st.rerun()
        except Exception:st.error('색인에 실패했습니다. API·모델 설정과 네트워크를 확인하세요.')
    team=st.selectbox('구단 계보',list(dict.fromkeys(x['franchise'] for x in all_items)),index=3)
    year=st.selectbox('시즌',list(range(2024,2014,-1)))
    chosen=next(x for x in all_items if x['franchise']==team and x['year']==year)
    if 'selected_id' not in st.session_state:st.session_state.selected_id=chosen['id']
    if st.session_state.get('_previous_choice')!=chosen['id']:
        st.session_state.selected_id=chosen['id'];st.session_state._previous_choice=chosen['id']
    method=st.radio('검색 방법',['similarity','mmr'],horizontal=True)
    online_docs=st.checkbox('질문마다 위키백과 자료 확장',disabled=cfg.mode!='online')
    st.caption('제공 자료 모드로도 질문할 수 있습니다. 설정 변경은 settings.json에 적용 후 재시작하세요.')
item=next(x for x in all_items if x['id']==st.session_state.selected_id)
explore,chat,inspect=st.tabs(['시즌 탐색','기록 질문','검색 비교'])
with explore:
    st.subheader('어떤 시즌이 궁금한가요?')
    condition=st.text_input('조건 입력',placeholder='2023년 우승 구단 / 2024년 서울 구단')
    if st.button('조건으로 찾기'):
        try:st.session_state.candidates=discover(store,condition)
        except Exception:st.error('탐색에 실패했습니다. 색인 및 API 설정을 확인하세요.')
    candidates=st.session_state.get('candidates',[])
    if condition and not candidates:st.caption('일치하는 결과가 없습니다. 데모에서는 연도·지역·구단명·N위·우승을 지원합니다.')
    for c in candidates:
        with st.container(border=True):
            a,b=st.columns([4,1]);a.markdown('**'+c['name']+'**');a.caption(f"{c['city']} · 최종 {c['final_rank']}위")
            if b.button('선택',key='pick'+c['id']):st.session_state.selected_id=c['id'];st.rerun()
with chat:
    st.subheader(item['name'])
    st.caption('최종 순위와 정규시즌 순위를 구분합니다. 문서에 없는 기록은 확인 불가로 답합니다.')
    histories=st.session_state.setdefault('histories',{});history=histories.setdefault(item['id'],[])
    for message in history:
        with st.chat_message(message['role']):
            st.write(message['text'])
            if message['role']=='assistant':
                if not message.get('sources'):st.caption('답변에 인용된 근거가 없습니다.')
                for e in message.get('sources',[]):
                    with st.expander(f"[근거 {e['number']}] {e['metadata']['title']}"):
                        st.caption(e['metadata']['source_type']);st.write(e['text']);st.link_button('원문 출처',e['metadata']['source'])
    guide=st.button('⚾ 이 시즌 입문 가이드')
    q=st.chat_input('예: 이 시즌 최종 순위는?')
    if guide:q='이 시즌 입문 가이드를 만들어줘. 최종 순위와 순위 읽는 법을 알려줘.'
    if q:
        if store.meta.count()==0:st.warning('색인이 없습니다. 왼쪽의 데이터 색인 버튼을 먼저 누르세요.')
        else:
            try:
                with st.status('문서 준비 중…',expanded=True) as status:
                    report=Collector(cfg,store).collect(item,q,status.write,online_docs)
                    status.write('수집 문서: '+', '.join(report['accepted']))
                    status.write('캐시 사용: '+str(report['cache_hits']))
                    if report['queries']:status.write('검색어: '+', '.join(report['queries']))
                    if report['rejected']:status.write('제외 후보: '+', '.join(report['rejected']))
                    status.write('근거 검색 및 답변 생성 중…')
                    result=rag.ask(item,q,method)
                    status.update(label='답변 완료',state='complete')
                history.extend([{'role':'user','text':q},{'role':'assistant','text':result['answer'],'sources':result['used']}]);st.rerun()
            except Exception:st.error('처리하지 못했습니다. API·모델 설정, 호출 한도, 문서 출처 연결을 확인한 후 다시 시도하세요.')
with inspect:
    st.subheader('유사도 검색과 MMR 비교')
    compare_q=st.text_input('비교 질문',value='이 시즌의 최종 순위와 특징은?')
    if st.button('같은 질문으로 검색 비교'):
        for col,kind in zip(st.columns(2),['similarity','mmr']):
            with col:
                st.markdown('**'+kind+'**')
                try:
                    for row in store.query(store.docs,compare_q,cfg['top_k'],{'item_id':item['id']},kind):st.write(row['metadata']['title']);st.caption(row['text'])
                except Exception:st.error('검색에 실패했습니다. 색인 및 API 설정을 확인하세요.')
st.caption('독립 교육용 프로젝트 · KBO 공식 서비스 아님 · 순위: KBO 구단 변천사 / 위키백과 확장 자료는 CC BY-SA 조건 확인')
