"""
기아 타이거즈 득점 알림 (GitHub Actions 버전, KBO 공식 홈페이지 데이터)
- 텔레그램 토큰과 chat ID는 GitHub Secrets에 저장 (코드에 직접 쓰지 않음)
"""

import datetime
import os
import time

import requests

POLL_SECONDS = 30           # 경기 중 확인 주기(초)
ALERT_OPPONENT = True       # 상대 팀 득점도 알릴지
MAX_RUN_MINUTES = 340       # GitHub 실행 시간 제한(6시간) 안에서 종료

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TEAM_CODE = "HT"            # KIA 팀 코드
KST = datetime.timezone(datetime.timedelta(hours=9))
UA = (
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)

KBO_URL = "https://www.koreabaseball.com/ws/Main.asmx/GetKboGameList"
KBO_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx",
    "X-Requested-With": "XMLHttpRequest",
}

NAVER_URL = "https://api-gw.sports.naver.com/schedule/games"
NAVER_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://m.sports.naver.com/",
}
DONE = ("RESULT", "CANCEL")


def send_telegram(text):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("텔레그램 설정이 없습니다 (Secrets 확인).", flush=True)
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=15,
        )
        if r.status_code != 200:
            print("텔레그램 전송 실패:", r.text, flush=True)
            return False
        return True
    except Exception as e:
        print("텔레그램 전송 실패:", e, flush=True)
        return False


def notify(title, message):
    now = datetime.datetime.now(KST).strftime("%H:%M:%S")
    print(f"[{now}] {title} - {message}", flush=True)
    send_telegram(f"{title}\n{message}")


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


# ---------- KBO 공식 홈페이지 ----------
def fetch_kbo():
    today = datetime.datetime.now(KST).date().strftime("%Y%m%d")
    data = {"leId": "1", "srId": "0,1,3,4,5,6,7,8,9", "date": today}
    r = requests.post(KBO_URL, data=data, headers=KBO_HEADERS, timeout=20)
    r.raise_for_status()
    games = r.json().get("game", [])

    result = []
    for g in games:
        home, away = g.get("HOME_ID"), g.get("AWAY_ID")
        if TEAM_CODE not in (home, away):
            continue
        kia_home = home == TEAM_CODE
        home_score = to_int(g.get("B_SCORE_CN"))
        away_score = to_int(g.get("T_SCORE_CN"))

        state = str(g.get("GAME_STATE_SC", ""))
        cancel = str(g.get("CANCEL_SC_ID", "0"))
        if cancel not in ("0", "", "None"):
            status = "CANCEL"
        elif state == "1":
            status = "BEFORE"
        elif state == "3":
            status = "RESULT"
        elif state == "4":
            status = "CANCEL"
        else:
            status = "STARTED"

        inn = g.get("GAME_INN_NO")
        tb = g.get("GAME_TB_SC")
        inning = ""
        if inn and status == "STARTED":
            inning = f"{inn}회{'초' if tb == 'T' else '말' if tb == 'B' else ''}"

        result.append({
            "id": g.get("G_ID"),
            "status": status,
            "kia_home": kia_home,
            "kia": home_score if kia_home else away_score,
            "opp": away_score if kia_home else home_score,
            "opp_name": g.get("AWAY_NM" if kia_home else "HOME_NM", "상대팀"),
            "inning": inning,
        })
    return result


# ---------- 네이버 (예비) ----------
def fetch_naver():
    today = datetime.datetime.now(KST).date().isoformat()
    params = {
        "fields": "basic",
        "upperCategoryId": "kbaseball",
        "categoryId": "kbo",
        "fromDate": today,
        "toDate": today,
        "size": 50,
    }
    r = requests.get(NAVER_URL, params=params, headers=NAVER_HEADERS, timeout=20)
    r.raise_for_status()
    games = r.json().get("result", {}).get("games", [])

    result = []
    for g in games:
        if TEAM_CODE not in (g.get("homeTeamCode"), g.get("awayTeamCode")):
            continue
        kia_home = g.get("homeTeamCode") == TEAM_CODE
        result.append({
            "id": g.get("gameId"),
            "status": g.get("statusCode", ""),
            "kia_home": kia_home,
            "kia": to_int(g.get("homeTeamScore" if kia_home else "awayTeamScore")),
            "opp": to_int(g.get("awayTeamScore" if kia_home else "homeTeamScore")),
            "opp_name": g.get("awayTeamName" if kia_home else "homeTeamName", "상대팀"),
            "inning": g.get("statusInfo", ""),
        })
    return result


def make_score_text(g):
    """원정팀(초)을 왼쪽, 홈팀(말)을 오른쪽에 표시"""
    if g["kia_home"]:
        away_name, away_score = g["opp_name"], g["opp"]
        home_name, home_score = "KIA", g["kia"]
    else:
        away_name, away_score = "KIA", g["kia"]
        home_name, home_score = g["opp_name"], g["opp"]
    text = f"{away_name}(초) {away_score} : {home_score} {home_name}(말)"
    if g["inning"]:
        text += f" ({g['inning']})"
    return text


def fetch_kia_games():
    try:
        return fetch_kbo()
    except Exception as e:
        print("KBO 데이터 실패, 네이버로 시도:", e)
    return fetch_naver()


def main():
    deadline = time.time() + MAX_RUN_MINUTES * 60
    print("KIA 득점 알림 시작", flush=True)

    games = fetch_kia_games()
    if not games:
        print("오늘 KIA 경기가 없습니다. 종료합니다.", flush=True)
        return
    if all(g["status"] in DONE for g in games):
        print("오늘 KIA 경기는 이미 끝났습니다. 종료합니다.", flush=True)
        return

    last = {}
    finished = set()

    while time.time() < deadline:
        try:
            games = fetch_kia_games()
            for g in games:
                gid, status = g["id"], g["status"]
                if status == "BEFORE" or gid in finished:
                    continue
                kia, opp, opp_name = g["kia"], g["opp"], g["opp_name"]
                text = make_score_text(g)

                if gid not in last:
                    last[gid] = (kia, opp)
                    if status in DONE:
                        finished.add(gid)
                        continue
                    if kia == 0 and opp == 0:
                        notify("⚾ KIA 경기 시작!", text)
                    else:
                        notify("⚾ KIA 경기 확인 시작", text)
                    continue

                prev_kia, prev_opp = last[gid]
                if kia > prev_kia:
                    notify(f"🐯 KIA 득점! (+{kia - prev_kia})", text)
                if ALERT_OPPONENT and opp > prev_opp:
                    notify(f"😣 {opp_name} 득점 (+{opp - prev_opp})", text)
                last[gid] = (kia, opp)

                if status in DONE:
                    finished.add(gid)
                    if status == "CANCEL":
                        notify("☔ KIA 경기 취소", text)
                    elif kia > opp:
                        notify("🎉 경기 종료 - KIA 승리!", text)
                    elif kia < opp:
                        notify("경기 종료 - KIA 패배", text)
                    else:
                        notify("경기 종료 - 무승부", text)

            if games and all(g["status"] in DONE for g in games):
                print("오늘 KIA 경기가 모두 끝났습니다.", flush=True)
                return

        except Exception as e:
            print("확인 중 오류:", e, flush=True)

        time.sleep(POLL_SECONDS)

    print("실행 시간 제한에 도달해 종료합니다.", flush=True)


if __name__ == "__main__":
    main()
