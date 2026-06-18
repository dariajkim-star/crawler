import streamlit as st #py frontend 
#풍선소환ㅋ_ㅋ
#st.balloons()

#1. 헤더랑 타이틀 같은 큰 글씨 적용하기
st.title("타이틀임")
st.header("이거슨 헤더")
st.subheader("좀더작은헤더임")

#2. 택스트를 입력해보자
#1. text
# 문자열임. 중간에 변수 안됨. 고정된 형식
st.text("고정된 형식의 문자 표시")
#2. write
#유연한 표현, 입력 데이터에 따라 자동으로 적절한 형식 지정이 필요할 때
#df도 표시 가능, 문자열, 리스트 ..
color = 'violet'
st.write(color)

#3. 마크다운 (.md)
#colab, README.md
st.markdown("https://naver.com")
st.markdown('[naver](https://naver.com)')

#4. html

html_page = """
<div style="background-color:#A7ABDE;padding:50px">
	<p style="color:#ECF2F5;font-size:5'px">Enjoy Streamlit!</p>
</div>
"""
#markdown에 html 삽입, unsafe_allow_html
st.markdown(html_page, unsafe_allow_html=True)

#5. 반응
st.success("성공")
st.warning("주의 좀")
st.error("에러다!!!!!")
st.info("정보전달")

#6. 미디어 연결
#pillow 라이브러리 사진컨트롤
from PIL import Image

#Image.open("./파일이름") 
img = Image.open("./낙타.png")
st.image(img, width=300, caption='hi')

#비디오 파일을 소장 -> 경로로 연결
#r(read), w(write), x(access) 
#rb -> read binary
#wb로 바꾸면 뭔가 쓸 수 있음
#video_file = open('경로', 'rb')
#video_binary = video_file.read()
#st.video(video_binary)

#유튜브 주소로 (영상주소)
st.video('https://youtu.be/934t54f-epE?si=h7xGKVB0xeBRi5Wy')

#오디오 파일
#audio_file = open('경로', 'rb')
#audio_binary = audio_file.read()
#st.audio(audio_binary)

#상호작용
#1. 클릭
#버튼이 눌리면 파일을 동작해
#if st.button("절대 누르지마셈ㅋㅋ"):
#    st.balloons()

#2. 체크박스
#if st.checkbox("동의합니다"):
#    st.info("전 재산을 정은이에게 넘기는 것을 동의합니다")

#3. 라디오박스
#radio_button = st.radio("밸런스게임 ㄱ", ['먹어도 살안찌기', '얼굴 자동 리프팅'])
#if radio_button == '먹어도 살안찌기':
#    st.success ('마운자로 맞으세요')

#else :
#    st.warning ('울세라 맞으세요')
#    st.button('피부과 회원권 결제 ㄱ')

#4. select box
#city = st.selectbox ('거주지를 고르세요',
#                     ['용산구', '영등포구', '종로구'])

#다중선택
#job = st.multiselect('희망 직무 선택',
#                    ['데이터분석', '리서치애널리스트', 'AI', '회계'])

#5. 텍스트 입력
#1. text_input: 한줄 입력 e.g. 이름, 메일주소
#email = st.text_input("메일 주소 입력 ㄱ", 
#              placeholder='daria.j.kim@gmail.com')

#if st.button('입력'):
#    st.write(email)

#2. text_area: 댓글 쓰기, 설명, 피드백
#reply = st.text_area('댓글을 달아주세요', placeholder='예시')

#단 자료형은 모두 같게
#number = st.number_input('나이를 입력하시오',
#                         min_value=1,
#                         max_value=99, 
#                         step=1)

#슬라이더
#val = st.slider('값을 선택하시오', 0, 10)
#st.write(val)

#시간표시
#import datetime
#import time
#from date time import datetime

#today = st.date_input('Today is', datetime.datetime.now())
#st.write(today)

#시간입력
#hour = st.time_input('the time is', datetime.time(12,30))

#현재시간 입력
#hour = st.time_input('the time is', datetime.now())


#reference https://docs.streamlit.io/develop/api-reference/charts
#그래프 그리기
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_csv('./gapminder.tsv', sep='\t')
#st.dataframe(df)

bar=sns.barplot(df, x='country', y='pop', color = '#A7ABDE')
#plt.show() = st.pyplot()
st.pyplot()

#streamlit으로 그리기
#이게 더 예쁘다, 그래프 바로 저장 가능 ... 누르셈.
st.bar_chart(df, x='country', y='pop', color = '#99AC73')

#----------------------------------------------------------
#JSON
data = {'name':'cookie', 'surname' : 'Dubai'}
st.json(data)

codes = '''
import as

path = os.path.join(origin, 'train.csv')


'''

st.code(codes, language='python')

#progress bar (UI/UX) -> tqdm
import time
#my_bar = st.progress(0)
#for v in range(100):
#    time.sleep(1)

#    my_bar.progress(v+1)


with st.spinner("기다리셈"):
    time.sleep(10)
st.success("다됐지롱")