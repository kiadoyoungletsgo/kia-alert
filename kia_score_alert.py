"""
기아 타이거즈 득점 알림 프로그램
- 네이버 스포츠 KBO 일정/스코어 데이터를 주기적으로 확인
- KIA 또는 상대 팀이 점수를 내면 알림 (PC 알림 + 선택: 텔레그램)

설치:  pip install requests plyer
실행:  python kia_score_alert.py
"""

import datetime
import time

import requests

# ===== 설정 =====
TEAM_CODE = "HT"          # 네이버 스포츠의 KIA 팀 코드
POLL_SECONDS = 30         # 확인 주기(초)
ALERT_OPPONENT = True     # 상대 팀 득점도 알릴지

# 휴대폰으로 받고 싶으면 텔레그램 봇 정보 입력 (비워두면 사용 안 함)
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""
# =================

API_URL = "https://api-gw.sports.naver.com/schedule/games"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://m.sports.naver.com/",
}


def notify(title, message):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {title} - {message}")

    # PC 데스크톱 알림
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=10)
    except Exception:
        pass

    # 텔레그램 알림
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": f"{title}\n{message}"},
                timeout=10,
            )
        except Exception as e:
            print("텔레그램 전송 실패:", e)


def fetch_kia_games():
    today = datetime.date.today().isoformat()
    params = {
        "fields": "basic",
        "upperCategoryId": "kbaseball",
        "categoryId": "kbo",
        "fromDate": today,
        "toDate": today,
        "size": 50,
    }
    r = requests.get(API_URL, params=params, headers=HEADERS, timeout=10)
    r.raise_for_status()
    games = r.json().get("result", {}).get("games", [])
    return [
        g for g in games
        if TEAM_CODE in (g.get("homeTeamCode"), g.get("awayTeamCode"))
    ]


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def main():
    print("KIA 득점 알림 시작 (종료: Ctrl+C)")
    last = {}          # gameId -> (KIA 점수, 상대 점수)
    finished = set()

    while True:
        try:
            games = fetch_kia_games()
            if not games:
                print("오늘 KIA 경기가 없습니다. 10분 후 다시 확인합니다.")
                time.sleep(600)
                continue

            for g in games:
                gid = g.get("gameId")
                status = g.get("statusCode", "")
                kia_home = g.get("homeTeamCode") == TEAM_CODE
                kia_score = to_int(g.get("homeTeamScore" if kia_home else "awayTeamScore"))
                opp_score = to_int(g.get("awayTeamScore" if kia_home else "homeTeamScore"))
                opp_name = g.get("awayTeamName" if kia_home else "homeTeamName", "상대팀")
                inning = g.get("statusInfo", "")
                score_text = f"KIA {kia_score} : {opp_score} {opp_name} ({inning})"

                if status == "BEFORE":
                    continue

                if gid not in last:
                    last[gid] = (kia_score, opp_score)
                    notify("⚾ KIA 경기 확인 중", score_text)
                    continue

                prev_kia, prev_opp = last[gid]
                if kia_score > prev_kia:
                    notify(f"🐯 KIA 득점! (+{kia_score - prev_kia})", score_text)
                if ALERT_OPPONENT and opp_score > prev_opp:
                    notify(f"😣 {opp_name} 득점 (+{opp_score - prev_opp})", score_text)
                last[gid] = (kia_score, opp_score)

                if status == "RESULT" and gid not in finished:
                    finished.add(gid)
                    if kia_score > opp_score:
                        result = "승리 🎉"
                    elif kia_score < opp_score:
                        result = "패배"
                    else:
                        result = "무승부"
                    notify(f"경기 종료 - KIA {result}", score_text)

            if all(g.get("statusCode") in ("RESULT", "CANCEL") for g in games):
                print("오늘 KIA 경기가 모두 끝났습니다.")
                break

        except Exception as e:
            print("확인 중 오류:", e)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
