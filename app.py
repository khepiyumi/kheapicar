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

# [상태 유지] 기록 데이터와 현재 조회 번호를 세션에 저장
if 'check_history' not in st.session_state:
    st.session_state.check_history = []
if 'current_car' not in st.session_state:
    st.session_state.current_car = None

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 관리 메뉴")
    if st.button("🏠 화면 초기화"):
        st.session_state.current_car = None
        st.rerun()
    st.markdown("---")
    if st.button("🗑️ 전체 기록 삭제"):
        st.session_state.check_history = []
        st.success("모든 기록이 삭제되었습니다.")
        st.rerun()

# CSS 스타일 (모바일 최적화 및 디자인)
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

# =========================
# 2. UI 구성 (탭)
# =========================
st.markdown('<p class="main-title">🚗 KHEPI 차량 2부제 점검 시스템</p>', unsafe_allow_html=True)
tab1, tab2, tab3 = st.tabs(["🔍 차량 조회/인식", "📊 점검 누적 목록", "📖 이용 가이드"])

# [탭 1] 입력 및 인식
with tab1:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("⌨️ 직접 입력")
        input_num = st.text_input("번호 뒤 4자리 입력", max_chars=4, placeholder="예: 1234")
        if st.button("번호로 조회"):
            if input_num:
                st.session_state.current_car = input_num.strip().zfill(4)
            else:
                st.warning("번호를 입력하세요.")

    with col2:
        st.subheader("📷 사진 인식")
        up_file = st.file_uploader("번호판 촬영/업로드", type=["jpg", "png", "jpeg"])
        if up_file:
            img_array = np.frombuffer(up_file.read(), np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            
            # 이미지 최적화 (해상도 축소)
            h, w = img.shape[:2]
            if w > 1000:
                img = cv2.resize(img, (1000, int(h * 1000 / w)))
            
            st.image(img, width=180, caption="업로드된 사진")
            
            if st.button("사진에서 번호 추출"):
                with st.spinner("분석 중..."):
                    results = reader.readtext(img)
                    detected = "".join([r[1] for r in results])
                    nums = re.findall(r'\d+', detected)
                    if nums:
                        st.session_state.current_car = "".join(nums)[-4:]
                        st.toast("번호 인식 성공!")
                    else:
                        st.error("번호를 찾지 못했습니다.")

# =========================
# 3. 판별 결과 및 기록 저장 (핵심 로직)
# =========================
if st.session_state.current_car:
    st.markdown("---")
    search_target = st.session_state.current_car
    result = df[df['car_number'] == search_target]

    # 한국 시간 기준 계산
    now_utc = datetime.datetime.utcnow()
    korea_time = now_utc + datetime.timedelta(hours=9)
    is_date_even = (korea_time.day % 2 == 0)
    day_type = "짝수" if is_date_even else "홀수"
    
    last_digit = int(search_target[-1])
    is_car_even = (last_digit % 2 == 0)
    is_violation = (is_date_even != is_car_even)

    # 결과 화면 표시
    st.subheader(f"🔍 조회 결과: {search_target}")
    
    if not result.empty:
        row = result.iloc[0]
        name_val, dept_val = row['name'], row['department']
        st.success(f"**✅ 등록 직원:** {name_val} ({dept_val})")
    else:
        name_val, dept_val = "미등록", "외부/미등록"
        st.error("**❌ 미등록 차량입니다.**")

    # 홀짝 판정 결과
    res_status = "🚨 운행 위반" if is_violation else "✅ 정상 운행"
    st.info(f"**오늘({korea_time.day}일, {day_type}날) 판정: {res_status}**")

    # [중요] 기록하기 버튼 - 클릭 시 세션 리스트에 추가
    if st.button("📋 이 결과를 점검 목록에 기록하기", type="primary"):
        new_data = {
            "점검시간": korea_time.strftime("%H:%M:%S"),
            "차량번호": search_target,
            "성명": name_val,
            "부서": dept_val,
            "판정": "위반" if is_violation else "정상"
        }
        st.session_state.check_history.append(new_data)
        st.success("✅ 점검 목록에 기록되었습니다! [점검 누적 목록] 탭에서 확인하세요.")

# =========================
# 4. [탭 2] 점검 기록 관리
# =========================
with tab2:
    st.subheader("📊 오늘의 점검 내역")
    if st.session_state.check_history:
        history_df = pd.DataFrame(st.session_state.check_history)
        st.dataframe(history_df, use_container_width=True)
        
        # CSV 다운로드
        csv = history_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 점검 기록 다운로드 (CSV)",
            data=csv,
            file_name=f"khepi_check_{korea_time.strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.write("아직 기록된 데이터가 없습니다.")

# [탭 3] 가이드
with tab3:
    st.info("💡 **도움말**\n\n1. 본사이는 차량2부제 시행에 따라 KHEPI 직원차량을 확인하기 위한 사이트입니다. \n2. 2부제 점검으로 날짜가 홀수인날은 차번호 짝수는 위반입니다. 날짜가 짝수인날은 차번호 홀수가 위반입니다. \n3. 차량 번호를 입력하거나 사진을 찍어 조회하세요.\n4. 결과가 나오면 '기록하기' 버튼을 눌러 목록에 저장할 수 있습니다.\n5. 저장된 목록은 브라우저를 닫기 전까지 유지되며, CSV로 저장 가능합니다.")
