import streamlit as st
import easyocr
import cv2
import pandas as pd
import numpy as np
import re
import datetime

# =========================
# 1. 설정 및 DB 로드
# =========================
st.set_page_config(page_title="차량판별 시스템", layout="wide")

# [추가] 점검 기록을 저장할 세션 상태 초기화
if 'check_history' not in st.session_state:
    st.session_state.check_history = []

with st.sidebar:
    st.header("⚙️ 설정")
    if st.button("🏠 메인 화면으로 돌아가기"):
        st.rerun()
    st.markdown("---")
    if st.button("🗑️ 전체 기록 초기화"):
        st.session_state.check_history = []
        st.success("모든 기록이 삭제되었습니다.")
        st.rerun()

# CSS 스타일링
st.markdown("""
    <style>
    .main-title { font-size: 24px !important; font-weight: bold; margin-bottom: 10px; }
    .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; font-weight: bold; }
    div[data-testid="stMetric"] { background-color: #f8f9fa; padding: 15px; border-radius: 10px; border: 1px solid #dee2e6; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data
def load_db():
    try:
        df = pd.read_csv("car_db.csv")
        df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        df = df.dropna(subset=['car_number'])
        def format_car_num(val):
            try:
                return str(int(float(val))).zfill(4)
            except:
                return str(val).strip().zfill(4)
        df['car_number'] = df['car_number'].apply(format_car_num)
        return df
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

df = load_db()

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['ko', 'en'])

reader = load_ocr()

# =========================
# 2. UI 구성 (상단 타이틀 및 탭)
# =========================
st.markdown('<p class="main-title">🚗 KHEPI 2부제 점검 관리 시스템</p>', unsafe_allow_html=True)

tab1, tab2, tab3, tab4 = st.tabs(["⌨️ 직접 입력", "📷 사진 인식", "📊 점검 기록", "📖 이용 가이드"])

car_number = None

# [탭 1] 직접 입력
with tab1:
    input_number = st.text_input("차량 번호 뒤 4자리 입력", max_chars=4, placeholder="예: 4348")
    if st.button("조회하기", key="btn_input"):
        if input_number:
            car_number = input_number
        else:
            st.warning("번호를 입력해주세요.")

# [탭 2] 사진 인식
with tab2:
    uploaded_file = st.file_uploader("번호판 촬영 또는 업로드", type=["jpg", "png", "jpeg"])
    if uploaded_file:
        img_array = np.frombuffer(uploaded_file.read(), np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is not None:
            height, width = img.shape[:2]
            if width > 1000:
                ratio = 1000 / width
                img = cv2.resize(img, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA)
            st.image(img, width=200, caption="인식된 이미지")
            with st.spinner("이미지 분석 중..."):
                try:
                    results = reader.readtext(img)
                    detected_text = "".join([r[1] for r in results])
                    numbers = re.findall(r'\d+', detected_text)
                    if numbers:
                        full_number = "".join(numbers)
                        car_number = full_number[-4:] if len(full_number) >= 4 else full_number
                        st.toast(f"인식 성공: {car_number}")
                    else:
                        st.warning("번호를 찾지 못했습니다.")
                except Exception as e:
                    st.error(f"분석 에러: {e}")

# [탭 4] 이용 가이드 (순서 변경)
with tab4:
    st.info("### 💡 시스템 사용법")
    st.markdown("""
    1. **점검 기록**: 조회된 차량은 하단의 '기록에 추가' 버튼을 눌러 목록에 쌓을 수 있습니다.
    2. **데이터 저장**: '점검 기록' 탭에서 누적된 명단을 확인하고 엑셀(CSV)로 다운로드하세요.
    """)

# =========================
# 3. 결과 출력 및 홀짝제 판별 로직
# =========================
if car_number:
    # 1. 차량 번호 형식 정리
    search_target = str(car_number).strip().zfill(4)
    result = df[df['car_number'] == search_target]

    # 2. 시간 및 홀짝 판별
    now_utc = datetime.datetime.utcnow()
    korea_time = now_utc + datetime.timedelta(hours=9)
    today_day = korea_time.day
    is_date_even = (today_day % 2 == 0)
    day_type_str = "짝수" if is_date_even else "홀수"
    
    last_digit = int(search_target[-1])
    is_car_even = (last_digit % 2 == 0)
    is_violation = (is_date_even != is_car_even)

    # 3. 결과 데이터 준비 (나중에 저장하기 위함)
    name_val = result.iloc[0]['name'] if not result.empty else "미등록"
    dept_val = result.iloc[0]['department'] if not result.empty else "외부/미등록"
    status_val = "위반" if is_violation else "정상"

    st.markdown("---")
    
    # [화면 표시] 등록 정보 및 결과
    if not result.empty:
        st.success(f"### ✅ 등록 차량 확인: {search_target}")
        c1, c2 = st.columns(2)
        with c1: st.markdown(f"**👤 성명:** {name_val}")
        with c2: st.markdown(f"**🏢 소속:** {dept_val}")
    else:
        st.error(f"### ❌ 미등록 차량: {search_target}")
        st.write("방문객 안내 대상을 확인해 주세요.")

    status_color = "🚨" if is_violation else "✅"
    st.info(f"{status_color} **오늘({day_type_str}날) 결과:** {status_val} (끝자리 {last_digit})")

    # [중요] 4. 기록 추가 버튼 (들여쓰기 주의!)
    # 버튼 클릭 시 리스트에 데이터를 넣습니다. 
    # key값에 타임스탬프를 넣어 중복 에러를 방지합니다.
    btn_key = f"save_{search_target}_{datetime.datetime.now().strftime('%H%M%S')}"
    
    if st.button("📋 이 결과를 점검 목록에 기록하기", key=btn_key):
        new_entry = {
            "점검시간": korea_time.strftime("%H:%M:%S"),
            "차량번호": search_target,
            "성명": name_val,
            "부서": dept_val,
            "판정": status_val
        }
        # st.session_state에 데이터 추가
        st.session_state.check_history.append(new_entry)
        st.success("✅ '점검 기록' 탭에 저장되었습니다!")
       

# =========================
# 4. [새로운 탭] 점검 기록 관리
# =========================
with tab3:
    st.markdown("### 📋 오늘의 점검 누적 목록")
    if st.session_state.check_history:
        history_df = pd.DataFrame(st.session_state.check_history)
        
        # 표 출력
        st.dataframe(history_df, use_container_width=True)
        
        # 다운로드 기능
        csv = history_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 현재 기록 엑셀(CSV) 다운로드",
            data=csv,
            file_name=f"check_report_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.write("아직 기록된 점검 내역이 없습니다.")
