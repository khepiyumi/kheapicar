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

# 기록 데이터, 개별 조회 번호, 일괄 처리 리스트 저장
if 'check_history' not in st.session_state:
    st.session_state.check_history = []
if 'current_car' not in st.session_state:
    st.session_state.current_car = None
# 일괄 처리 결과 (이미지 포함)
if 'batch_visual_results' not in st.session_state:
    st.session_state.batch_visual_results = []

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 관리 메뉴")
    if st.button("🏠 화면 초기화"):
        st.session_state.current_car = None
        st.session_state.batch_visual_results = []
        st.rerun()
    st.markdown("---")
    if st.button("🗑️ 전체 기록 삭제"):
        st.session_state.check_history = []
        st.session_state.batch_visual_results = []
        st.success("모든 기록이 삭제되었습니다.")
        st.rerun()

# CSS 스타일
st.markdown("""
    <style>
    .main-title { font-size: 24px !important; font-weight: bold; margin-bottom: 15px; color: #1E3A8A; }
    .stButton>button { width: 100%; border-radius: 10px; font-weight: bold; }
    /* 썸네일 카드 스타일 */
    .thumb-card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 10px;
        background-color: white;
        text-align: center;
        margin-bottom: 10px;
    }
    .thumb-img {
        max-width: 100%;
        height: auto;
        border-radius: 5px;
        margin-bottom: 5px;
    }
    .result-text {
        font-weight: bold;
        font-size: 14px;
    }
    </style>
    """, unsafe_allow_html=True)

# =========================
# 유틸리티 함수
# =========================

# DB 로드 함수
@st.cache_data
def load_db():
    try:
        # 실제 환경에서는 car_db.csv가 필요합니다.
        # 테스트를 위해 더미 데이터를 생성합니다. (실제 배포시에는 이 블록 삭제)
        try:
            df = pd.read_csv("car_db.csv")
        except FileNotFoundError:
            data = {
                'car_number': ['1234', '5678', '9012', '3456'],
                'name': ['홍길동', '김철수', '이영희', '박민수'],
                'department': ['운영팀', '인사팀', '개발팀', '외부위탁']
            }
            df = pd.DataFrame(data)
            df.to_csv("car_db.csv", index=False, encoding='utf-8-sig')

        df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        df = df.dropna(subset=['car_number'])
        def format_car_num(val):
            try: return str(int(float(val))).zfill(4)
            except: return str(val).strip().zfill(4)
        df['car_number'] = df['car_number'].apply(format_car_num)
        return df
    except Exception as e:
        st.error(f"DB 로드 실패: {e}"); st.stop()

# OCR 로드 함수
@st.cache_resource
def load_ocr():
    return easyocr.Reader(['ko', 'en'])

# 공통 로직: 2부제 판정 함수
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

# 이미지를 base64로 인코딩하는 함수 (HTML 표시용)
def opencv_to_base64(image):
    _, buffer = cv2.imencode('.jpg', image)
    encoded_string = base64.b64encode(buffer).decode('utf-8')
    return f"data:image/jpeg;base64,{encoded_string}"

# 전역 변수 초기화
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
            input_num = st.text_input("번호 뒤 4자리 입력", max_chars=4, key="single_input")
            if st.button("조회"):
                st.session_state.current_car = input_num.strip().zfill(4)

        with col2:
            st.subheader("📷 사진 인식")
            up_file = st.file_uploader("사진 업로드", type=["jpg", "png", "jpeg"], key="single_file")
            if up_file:
                # 파일 버퍼에서 직접 읽기
                file_bytes = np.frombuffer(up_file.read(), np.uint8)
                img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                
                # 원본 표시 (너무 크면 가로폭 제한)
                st.image(img, channels="BGR", width=300, caption="업로드된 이미지")
                
                with st.spinner("분석 중..."):
                    results = reader.readtext(img)
                    # 전처리: 숫자만 추출 후 마지막 4자리
                    detected_text = "".join([r[1] for r in results])
                    nums = re.findall(r'\d+', detected_text)
                    
                    if nums:
                        # 인식된 전체 숫자 중 가장 마지막 4자리 선택 (통상 번호판 마지막 번호)
                        st.session_state.current_car = "".join(nums)[-4:]
                        st.toast(f"✅ 인식 성공: {st.session_state.current_car}")
                    else:
                        st.error("숫자를 인식하지 못했습니다.")

        # 결과 표시 (개별)
        if st.session_state.current_car:
            st.markdown("---")
            car_num = st.session_state.current_car
            is_violation, k_time, day_type = check_violation(car_num)
            
            res_db = df[df['car_number'] == car_num]
            name = res_db.iloc[0]['name'] if not res_db.empty else "미등록"
            dept = res_db.iloc[0]['department'] if not res_db.empty else "외부/미등록"
            
            st.write(f"### 결과: {car_num}")
            
            if not res_db.empty:
                st.success(f"✅ 등록 직원: {name} ({dept})")
            else:
                st.error(f"❌ {name} 차량입니다.")

            if is_violation: 
                st.warning(f"🚨 금일은 **[{day_type}날]**로 운행 위반입니다.")
            else: 
                st.info(f"✅ 금일은 **[{day_type}날]**로 정상 운행입니다.")

            if st.button("📋 기록하기", type="primary"):
                st.session_state.check_history.append({
                    "점검시간": k_time.strftime("%H:%M:%S"),
                    "차량번호": car_num, "성명": name, "부서": dept, 
                    "판정": "위반" if is_violation else "정상"
                })
                st.toast(f"{car_num} 기록 완료!")
                st.session_state.current_car = None # 처리 후 초기화
                st.rerun()

    else:
        st.subheader("📑 일괄 처리 모드")
        m_col1, m_col2 = st.columns(2)
        
        with m_col1:
            st.markdown("**1. 텍스트 일괄 입력**")
            bulk_text = st.text_area("번호판 4자리를 쉼표, 공백, 줄바꿈 등으로 구분하여 입력", height=120, placeholder="예: 1234, 5678\n9012")
            if st.button("텍스트 일괄 분석"):
                nums = re.findall(r'\d{4}', bulk_text)
                temp_results = []
                for n in nums:
                    is_v, kt, _ = check_violation(n)
                    res_db = df[df['car_number'] == n]
                    temp_results.append({
                        "점검시간": kt.strftime("%H:%M:%S"), "차량번호": n,
                        "성명": res_db.iloc[0]['name'] if not res_db.empty else "미등록",
                        "부서": res_db.iloc[0]['department'] if not res_db.empty else "외부",
                        "판정": "위반" if is_v else "정상",
                        "type": "text" # 텍스트 입력 표시
                    })
                # 텍스트 결과는 기존 visual_results에 추가하지 않고 테이블로만 표시
                if temp_results:
                    st.session_state.batch_text_results = temp_results
                else:
                    st.warning("유효한 4자리 숫자를 찾지 못했습니다.")

        with m_col2:
            st.markdown("**2. 사진 일괄 업로드 (썸네일 표시)**")
            multi_files = st.file_uploader("사진 여러 장 선택", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="multi_file")
            
            if st.button("사진 일괄 분석") and multi_
