import streamlit as st
import easyocr
import cv2
import pandas as pd
import numpy as np
import re
import datetime
import base64

# =========================
# 1. 설정 및 세션 초기화
# =========================
st.set_page_config(page_title="KHEPI 차량 점검 시스템", layout="wide")

# 세션 상태 초기화 (텍스트/사진 결과 분리 저장)
if 'check_history' not in st.session_state:
    st.session_state.check_history = []
if 'current_car' not in st.session_state:
    st.session_state.current_car = None
if 'batch_text_results' not in st.session_state:
    st.session_state.batch_text_results = []
if 'batch_visual_results' not in st.session_state:
    st.session_state.batch_visual_results = []

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 관리 메뉴")
    if st.button("🏠 화면 초기화"):
        st.session_state.current_car = None
        st.session_state.batch_text_results = []
        st.session_state.batch_visual_results = []
        st.rerun()
    st.markdown("---")
    if st.button("🗑️ 전체 기록 삭제"):
        st.session_state.check_history = []
        st.success("모든 기록이 삭제되었습니다.")
        st.rerun()

# CSS 스타일
st.markdown("""
    <style>
    .main-title { font-size: 24px !important; font-weight: bold; margin-bottom: 15px; color: #1E3A8A; }
    .stButton>button { width: 100%; border-radius: 10px; font-weight: bold; }
    .thumb-card { border: 1px solid #ddd; border-radius: 10px; padding: 10px; background-color: white; text-align: center; margin-bottom: 10px; }
    .thumb-img { max-width: 100%; height: 100px; object-fit: contain; border-radius: 5px; margin-bottom: 5px; }
    .result-text { font-weight: bold; font-size: 13px; }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 유틸리티 함수
# =========================

@st.cache_data
def load_db():
    try:
        df = pd.read_csv("car_db.csv")
        df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        df = df.dropna(subset=['car_number'])
        def format_car_num(val):
            try: return str(int(float(val))).zfill(4)
            except: return str(val).strip().zfill(4)
        df['car_number'] = df['car_number'].apply(format_car_num)
        return df
    except Exception as e:
        st.error("car_db.csv 파일을 찾을 수 없습니다."); st.stop()

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['ko', 'en'])

def check_violation(car_num):
    now_utc = datetime.datetime.utcnow()
    korea_time = now_utc + datetime.timedelta(hours=9)
    is_date_even = (korea_time.day % 2 == 0)
    try:
        last_digit = int(car_num[-1])
        is_car_even = (last_digit % 2 == 0)
        is_violation = (is_date_even != is_car_even)
        return is_violation, korea_time, "짝수" if is_date_even else "홀수"
    except:
        return False, korea_time, "오류"

def opencv_to_base64(image):
    _, buffer = cv2.imencode('.jpg', image)
    return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"

df = load_db()
reader = load_ocr()

# =========================
# 2. UI 구성 (탭)
# =========================
st.markdown('<p class="main-title">🚗 KHEPI 차량 2부제 점검 시스템</p>', unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["🔍 차량 조회/인식", "📊 점검 누적 목록", "📖 이용 가이드"])

with tab1:
    mode = st.radio("입력 모드 선택", ["개별 확인", "일괄 처리 (여러 대)"], horizontal=True)
    
    if mode == "개별 확인":
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("⌨️ 직접 입력")
            input_num = st.text_input("번호 뒤 4자리 입력", max_chars=4)
            if st.button("단일 조회"):
                st.session_state.current_car = input_num.strip().zfill(4)

        with col2:
            st.subheader("📷 사진 인식")
            up_file = st.file_uploader("사진 업로드", type=["jpg", "png", "jpeg"], key="single")
            if up_file:
                img = cv2.imdecode(np.frombuffer(up_file.read(), np.uint8), cv2.IMREAD_COLOR)
                st.image(img, width=200, channels="BGR")
                if st.button("번호 추출"):
                    results = reader.readtext(img)
                    nums = re.findall(r'\d+', "".join([r[1] for r in results]))
                    if nums:
                        st.session_state.current_car = "".join(nums)[-4:]
                        st.toast(f"추출 성공: {st.session_state.current_car}")

        if st.session_state.current_car:
            st.markdown("---")
            car_num = st.session_state.current_car
            is_v, kt, d_type = check_violation(car_num)
            res_db = df[df['car_number'] == car_num]
            name = res_db.iloc[0]['name'] if not res_db.empty else "미등록"
            dept = res_db.iloc[0]['department'] if not res_db.empty else "외부"
            
            st.subheader(f"조회 결과: {car_num}")
            if is_v: st.error(f"🚨 운행 위반 (오늘은 {d_type}날)")
            else: st.success(f"✅ 정상 운행 (오늘은 {d_type}날)")
            st.write(f"**소속:** {dept} | **성명:** {name}")

            if st.button("📋 이 결과 저장하기", type="primary"):
                st.session_state.check_history.append({
                    "점검시간": kt.strftime("%H:%M:%S"), "차량번호": car_num,
                    "성명": name, "부서": dept, "판정": "위반" if is_v else "정상"
                })
                st.session_state.current_car = None
                st.rerun()

    else:
        st.subheader("📑 일괄 처리 모드")
        m_col1, m_col2 = st.columns(2)
        
        with m_col1:
            st.markdown("**1. 텍스트 입력 (번호 4자리 나열)**")
            bulk_text = st.text_area("쉼표, 엔터, 공백 등으로 구분 가능", placeholder="1234 5678 9012", height=150)
            if st.button("차번호 조회 시작"):
                nums = re.findall(r'\d{4}', bulk_text)
                if nums:
                    temp_res = []
                    for n in nums:
                        is_v, kt, _ = check_violation(n)
                        res_db = df[df['car_number'] == n]
                        temp_res.append({
                            "점검시간": kt.strftime("%H:%M:%S"), "차량번호": n,
                            "성명": res_db.iloc[0]['name'] if not res_db.empty else "미등록",
                            "부서": res_db.iloc[0]['department'] if not res_db.empty else "외부",
                            "판정": "위반" if is_v else "정상"
                        })
                    st.session_state.batch_text_results = temp_res
                    st.success(f"{len(nums)}대를 찾았습니다. 아래 표를 확인하세요.")
                else:
                    st.warning("4자리 숫자를 찾지 못했습니다.")

        with m_col2:
            st.markdown("**2. 사진 여러 장 업로드**")
            multi_files = st.file_uploader("여러 사진 선택", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
            if st.button("사진 일괄 분석 시작") and multi_files:
                st.session_state.batch_visual_results = []
                p_bar = st.progress(0)
                for i, f in enumerate(multi_files):
                    img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
                    if img is None: continue
                    
                    # 썸네일
                    thumb = cv2.resize(img, (200, int(img.shape[0] * (200 / img.shape[1]))))
                    b64_img = opencv_to_base64(thumb)
                    
                    ocr_res = reader.readtext(img)
                    found = re.findall(r'\d{4}', "".join([r[1] for r in ocr_res]))
                    n = found[-1] if found else "실패"
                    is_v, kt, _ = check_violation(n)
                    res_db = df[df['car_number'] == n]
                    
                    st.session_state.batch_visual_results.append({
                        "img_base64": b64_img, "점검시간": kt.strftime("%H:%M:%S"), "차량번호": n,
                        "성명": res_db.iloc[0]['name'] if not res_db.empty else "미등록",
                        "부서": res_db.iloc[0]['department'] if not res_db.empty else "외부",
                        "판정": "위반" if is_v else "정상" if found else "실패"
                    })
                    p_bar.progress((i + 1) / len(multi_files))

        # ---------------------------
        # [결과 출력 영역]
        # ---------------------------
        
        # 1. 텍스트 분석 결과 테이블
        if st.session_state.batch_text_results:
            st.markdown("---")
            st.write("### 📋 텍스트 분석 결과")
            st.table(pd.DataFrame(st.session_state.batch_text_results))
            if st.button("💾 위 텍스트 결과 모두 기록하기", type="primary"):
                st.session_state.check_history.extend(st.session_state.batch_text_results)
                st.session_state.batch_text_results = []
                st.success("누적 목록에 저장되었습니다.")
                st.rerun()

        # 2. 사진 분석 결과 (썸네일)
        if st.session_state.batch_visual_results:
            st.markdown("---")
            st.write("### 📷 사진 분석 결과")
            cols = st.columns(5)
            for idx, item in enumerate(st.session_state.batch_visual_results):
                color = "red" if item['판정'] == "위반" else "green" if item['판정'] == "정상" else "gray"
                with cols[idx % 5]:
                    st.markdown(f"""
                        <div class="thumb-card">
                            <img src="{item['img_base64']}" class="thumb-img">
                            <div class="result-text">{item['차량번호']}</div>
                            <div class="result-text" style="color: {color};">{item['판정']}</div>
                        </div>
                        """, unsafe_allow_html=True)
            
            if st.button("💾 위 사진 내역 모두 기록하기", type="primary"):
                for item in st.session_state.batch_visual_results:
                    if item['차량번호'] != "실패":
                        data = item.copy()
                        del data['img_base64']
                        st.session_state.check_history.append(data)
                st.session_state.batch_visual_results = []
                st.success("저장 완료!")
                st.rerun()

# =========================
# 3. [탭 2] 점검 기록 관리
# =========================
with tab2:
    st.subheader("📊 오늘의 점검 내역")
    if st.session_state.check_history:
        h_df = pd.DataFrame(st.session_state.check_history).iloc[::-1] # 최신순
        st.dataframe(h_df, use_container_width=True)
        csv = h_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 전체 기록 다운로드 (CSV)", data=csv, file_name=f"khepi_{datetime.datetime.now().strftime('%m%d')}.csv")
    else:
        st.write("기록이 없습니다.")

with tab3:
    st.info("차량 2부제 점검 가이드")
    st.markdown("1. **텍스트 입력**: 쉼표나 엔터로 구분된 4자리 숫자들을 한꺼번에 판별합니다.\n2. **사진 일괄 분석**: 여러 장의 사진을 썸네일과 함께 판별합니다.")
