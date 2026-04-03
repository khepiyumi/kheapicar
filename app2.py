import streamlit as st
import easyocr
import cv2
import pandas as pd
import numpy as np
import re
import datetime

# =========================
# 1. 설정 및 세션 초기화
# =========================
st.set_page_config(page_title="KHEPI 차량 점검 시스템", layout="wide")

# 기록 데이터, 개별 조회 번호, 일괄 처리 리스트 저장
if 'check_history' not in st.session_state:
    st.session_state.check_history = []
if 'current_car' not in st.session_state:
    st.session_state.current_car = None
if 'batch_results' not in st.session_state:
    st.session_state.batch_results = []

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 관리 메뉴")
    if st.button("🏠 화면 초기화"):
        st.session_state.current_car = None
        st.session_state.batch_results = []
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
    .status-box { padding: 10px; border-radius: 10px; border: 1px solid #eee; background-color: #f9f9f9; }
    </style>
    """, unsafe_allow_html=True)

# DB 로드 함수
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
        st.error(f"DB 로드 실패: {e}"); st.stop()

df = load_db()

# OCR 로드 함수
@st.cache_resource
def load_ocr():
    return easyocr.Reader(['ko', 'en'])
reader = load_ocr()

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
                img = cv2.imdecode(np.frombuffer(up_file.read(), np.uint8), cv2.IMREAD_COLOR)
                st.image(img, width=150)
                with st.spinner("분석 중..."):
                    results = reader.readtext(img)
                    nums = re.findall(r'\d+', "".join([r[1] for r in results]))
                    if nums:
                        st.session_state.current_car = "".join(nums)[-4:]
                        st.toast(f"✅ 인식 성공: {st.session_state.current_car}")

        # 결과 표시 (개별)
        if st.session_state.current_car:
            st.markdown("---")
            car_num = st.session_state.current_car
            is_violation, k_time, day_type = check_violation(car_num)
            
            res_db = df[df['car_number'] == car_num]
            name = res_db.iloc[0]['name'] if not res_db.empty else "미등록"
            dept = res_db.iloc[0]['department'] if not res_db.empty else "외부"
            
            st.write(f"### 결과: {car_num} ({name})")
            if is_violation: st.error(f"🚨 2부제 위반 ({day_type}날)")
            else: st.success(f"✅ 정상 운행 ({day_type}날)")

            if st.button("📋 기록하기"):
                st.session_state.check_history.append({
                    "점검시간": k_time.strftime("%H:%M:%S"),
                    "차량번호": car_num, "성명": name, "부서": dept, 
                    "판정": "위반" if is_violation else "정상"
                })
                st.toast("기록 완료!")

    else:
        st.subheader("📑 일괄 처리 모드")
        m_col1, m_col2 = st.columns(2)
        
        with m_col1:
            bulk_text = st.text_area("번호판 4자리를 나열하세요 (예: 1234 5678 9012)", height=150)
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
                        "판정": "위반" if is_v else "정상"
                    })
                st.session_state.batch_results = temp_results

        with m_col2:
            multi_files = st.file_uploader("사진 여러 장 업로드", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
            if st.button("사진 일괄 분석") and multi_files:
                temp_results = []
                p_bar = st.progress(0)
                for i, f in enumerate(multi_files):
                    img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
                    ocr_res = reader.readtext(img)
                    found = re.findall(r'\d{4}', "".join([r[1] for r in ocr_res]))
                    if found:
                        n = found[0]
                        is_v, kt, _ = check_violation(n)
                        res_db = df[df['car_number'] == n]
                        temp_results.append({
                            "점검시간": kt.strftime("%H:%M:%S"), "차량번호": n,
                            "성명": res_db.iloc[0]['name'] if not res_db.empty else "미등록",
                            "부서": res_db.iloc[0]['department'] if not res_db.empty else "외부",
                            "판정": "위반" if is_v else "정상"
                        })
                    p_bar.progress((i + 1) / len(multi_files))
                st.session_state.batch_results = temp_results

        if st.session_state.batch_results:
            st.markdown("---")
            st.write(f"### 📋 분석 결과 ({len(st.session_state.batch_results)}대)")
            batch_df = pd.DataFrame(st.session_state.batch_results)
            st.dataframe(batch_df, use_container_width=True)
            if st.button("💾 위 내역 모두 기록하기", type="primary"):
                st.session_state.check_history.extend(st.session_state.batch_results)
                st.session_state.batch_results = []
                st.success("누적 목록에 저장되었습니다.")
                st.rerun()

# =========================
# 3. [탭 2] 점검 기록 관리
# =========================
with tab2:
    st.subheader("📊 오늘의 점검 내역")
    if st.session_state.check_history:
        history_df = pd.DataFrame(st.session_state.check_history)
        st.dataframe(history_df, use_container_width=True)
        csv = history_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 CSV 다운로드", data=csv, file_name=f"khepi_{datetime.datetime.now().strftime('%Y%m%d')}.csv")
    else:
        st.write("기록된 내역이 없습니다.")

# =========================
# 4. [탭 3] 가이드
# =========================
with tab3:
    st.info("💡 **KHEPI 차량 2부제 일괄 처리 가이드**")
    st.markdown("""
    1. **텍스트 일괄 입력**: 메모장이나 메신저로 받은 여러 개의 번호를 복사해서 붙여넣으면 한꺼번에 판별합니다.
    2. **사진 일괄 업로드**: 카메라로 찍은 여러 장의 사진을 한 번에 선택하여 업로드하면 순차적으로 OCR 분석을 수행합니다.
    3. **저장 방식**: 분석된 결과는 '미리보기' 상태이며, 반드시 **[기록하기]** 버튼을 눌러야 최종 목록에 저장됩니다.
    """)
