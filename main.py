import time
import json
import requests
from google import genai
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# 1. GitHub 설정 정보
REPO_OWNER = "damjun0804-cell"
REPO_NAME = "dodam_game"
FILE_PATH = "game_config.json"

# 2. Gemini API 설정 (제공해주신 API 키 적용)
GEMINI_API_KEY = "AQ.Ab8RN6L5Kt-myAILHI6q8IBy2bYvDl049W-e8PPlMHwacNobEA"
client = genai.Client(api_key=GEMINI_API_KEY)

# 전역 설정 캐시 변수
game_config = {
    "is_game_active": True,
    "target_word": "",
    "forbidden_words": [],
    "system_instruction": "",
    "suspects": {}
}

def load_config_from_github():
    """GitHub에 저장된 game_config.json 파일을 실시간으로 불러옵니다."""
    global game_config
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            import base64
            file_content = base64.b64decode(data['content']).decode('utf-8')
            game_config = json.loads(file_content)
            print("[Config] 설정 파일을 성공적으로 불러왔습니다.")
        else:
            print(f"[Config] 설정 불러오기 실패 (상태 코드: {response.status_code})")
    except Exception as e:
        print(f"[Config] 설정 불러오기 중 오류 발생: {e}")

def save_winner(username, nickname):
    # 정답자 기록 로직
    pass

def get_ranking_text():
    return "현재 순위 정보입니다."

def get_gemini_ai_answer(question, config):
    """Gemini AI를 사용하여 JSON 설정 규칙과 용의자 정보를 바탕으로 답변을 생성합니다."""
    target_word = config.get("target_word", "")
    forbidden_words = config.get("forbidden_words", [])
    instruction = config.get("system_instruction", "당신은 추리 게임의 AI 캐릭터입니다.")
    suspects = config.get("suspects", {})

    # 금지어 체크
    for fw in forbidden_words:
        if fw in question:
            return f"⚠️ 금지어('{fw}')가 포함되어 있어 답변할 수 없습니다!"

    # 정답 직접 언급 체크
    if target_word and target_word in question:
        return "🤫 정답을 직접 유도하거나 물어보실 수 없습니다!"

    try:
        # Gemini에게 전달할 프롬프트 구성
        prompt = f"""
[시스템 지침]
{instruction}

[게임 설정 및 용의자 정보]
- 정답 단어(비밀): {target_word}
- 용의자 정보: {json.dumps(suspects, ensure_ascii=False)}

[청취자 질문]
{question}

위 지침과 정보를 바탕으로 청취자의 질문에 대해 흥미로운 추리 힌트나 캐릭터 답변을 1~2문장으로 짧게 작성해줘.
"""

        # Gemini 모델 호출 (최신 별칭 적용)
        response = client.models.generate_content(
            model='gemini-flash-latest',
            contents=prompt,
        )
        
        answer = response.text.strip()
        return answer
    except Exception as e:
        print(f"[AI Error] Gemini 답변 생성 중 오류 발생: {e}")
        return "죄송합니다. 잠시 후 다시 시도해주세요."

def send_chat_message(driver, message):
    """스푼라디오 실제 채팅 입력창(textarea)에 메시지를 입력하고 전송합니다."""
    try:
        selectors = [
            "textarea.sc-dhTHNW",
            ".chat-input-area textarea",
            "textarea[placeholder='대화를 입력하세요.']"
        ]
        
        input_box = None
        for selector in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    if elem.is_displayed():
                        input_box = elem
                        break
                if input_box:
                    break
            except:
                continue
                
        if not input_box:
            print("[Bot] 채팅 입력창(textarea)을 찾지 못했습니다.")
            return

        input_box.click()
        input_box.clear()
        input_box.send_keys(message)
        
        # 1. 엔터 키 전송 시도
        input_box.send_keys(Keys.RETURN)
        
        # 2. 전송 버튼 클릭 추가 시도
        try:
            send_btn = driver.find_element(By.CSS_SELECTOR, ".chat-input-area button")
            send_btn.click()
        except:
            pass

        print(f"[Bot] 채팅 전송 완료: {message}")
    except Exception as e:
        print(f"[Bot] 채팅 전송 중 오류 발생: {e}")

def run_browser_bot():
    driver = webdriver.Chrome()
    
    try:
        driver.get("https://www.spooncast.net/")
        print("[Bot] 브라우저가 실행되었습니다. 방송 페이지로 이동 후 로그인을 완료해주세요.")
        
        time.sleep(15)

        print("[Bot] 실시간 채팅 모니터링을 시작합니다...")
        
        processed_messages = set()
        last_config_load_time = 0

        while True:
            current_time = time.time()
            
            # 30초마다 GitHub에서 최신 설정 동기화
            if current_time - last_config_load_time > 30:
                load_config_from_github()
                last_config_load_time = current_time

            # 게임이 OFF 상태라면 채팅 감지를 건너뜀
            if not game_config.get("is_game_active", True):
                time.sleep(2)
                continue

            try:
                chat_elements = driver.find_elements(By.CSS_SELECTOR, ".live-detail-comment-list li[data-comment-type='message'], .live-detail-comment-list li[data-comment-type='combo']")

                for elem in chat_elements:
                    full_text = elem.text.strip()
                    if not full_text:
                        continue
                    
                    user_name = ""
                    content = ""
                    
                    try:
                        name_elements = elem.find_elements(By.CSS_SELECTOR, ".comment-name .name .text-box")
                        if name_elements:
                            user_name = name_elements[0].text.strip()
                        
                        if not user_name:
                            thumb_elements = elem.find_elements(By.CSS_SELECTOR, "button.thumbnail")
                            if thumb_elements:
                                user_name = thumb_elements[0].get_attribute("title").strip()

                        content_elements = elem.find_elements(By.CSS_SELECTOR, ".comment-text pre")
                        if content_elements:
                            content = content_elements[0].text.strip()
                        else:
                            lines = full_text.split("\n")
                            content = lines[-1].strip()

                    except Exception:
                        continue

                    if not user_name or not content:
                        continue

                    message_key = f"{user_name}:{content}"
                    
                    if message_key in processed_messages:
                        continue
                    
                    processed_messages.add(message_key)

                    if len(processed_messages) > 500:
                        processed_messages.clear()

                    print(f"[Chat 수신] {user_name}: {content}")

                    # 1. '!정답' 명령어 처리
                    if content.startswith("!정답"):
                        guess = content.replace("!정답", "").strip()
                        target_word = game_config.get("target_word", "")
                        
                        if target_word and guess == target_word:
                            save_winner(user_name, user_name)
                            print(f"[Game] 🏆 정답자 탄생! ({user_name})")
                        else:
                            print(f"[Game] 오답입니다: {user_name} (입력값: {guess})")

                    # 2. '!순위' 명령어 처리
                    elif content.startswith("!순위"):
                        ranking_msg = get_ranking_text()
                        print(f"[Game 순위 출력]: {ranking_msg}")

                    # 3. '!테스트' 명령어 처리 (하도담바보 전송)
                    elif content.startswith("!테스트"):
                        send_chat_message(driver, "하도담바보")

                    # 4. '!'로 시작하는 일반 추리 질문 처리 -> Gemini AI 연동 및 스푼 채팅창 전송
                    elif content.startswith("!") and not content.startswith("!정답") and not content.startswith("!순위") and not content.startswith("!테스트"):
                        question = content[1:] # '!'를 제외한 질문 텍스트
                        ai_reply = get_gemini_ai_answer(question, game_config)
                        print(f"[Gemini AI 답변 생성]: {ai_reply}")
                        
                        if ai_reply:
                            send_chat_message(driver, ai_reply)

                time.sleep(0.3)

            except Exception as loop_err:
                print(f"[루프 내 오류 발생]: {loop_err}")
                time.sleep(3)

    finally:
        driver.quit()

if __name__ == "__main__":
    load_config_from_github()
    run_browser_bot()
