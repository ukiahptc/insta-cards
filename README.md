# insta-cards — 노션 데일리 브리핑 → 인스타그램 자동 게시

매일 노션에 쌓이는 두 브리핑(AI 글로벌 트렌드 08시, 청년정책 09시)을 카드뉴스 이미지로 만들어
GitHub Pages에 올리고, Instagram Graph API로 캐러셀 게시하는 도구 모음이다.
실제 실행은 Claude 스케줄 태스크(`daily-instagram-ai-trend`, `daily-instagram-youth-policy`)가 `PIPELINE.md` 절차대로 한다.

```
tools/make_cards.py        카드 스펙 JSON → JPG (Apple SD Gothic Neo, 1080×1350)
tools/post_instagram.mjs   Graph API 게시 (아이템 컨테이너 → 캐러셀 → 발행)
tools/config.example.json  설정 파일 예시 → ~/.config/insta-agent/config.json 으로 복사해 채움
specs/                     날짜별 카드 스펙(.json) + 캡션(.caption.txt)
cards/                     생성된 이미지 (GitHub Pages로 공개됨)
PIPELINE.md                스케줄 태스크가 따르는 공용 절차
```

## 1회 설정 (사람이 직접)

### A. 인스타그램 계정을 프로페셔널로 전환
인스타 앱 → 프로필 → 오른쪽 위 ≡ → 설정 및 활동 → 계정 유형 및 도구 → 프로페셔널 계정으로 전환 (비즈니스 또는 크리에이터 아무거나).
개인 계정은 API 게시가 불가능하다.

### B. Meta 앱 만들기
1. https://developers.facebook.com/apps → 앱 만들기.
2. 사용 사례에서 **"Instagram 비즈니스 로그인으로 Instagram API 사용"** 선택 (앱 유형은 비즈니스). 앱 이름 아무거나. 만들기.
3. 왼쪽 메뉴 **Instagram → "Instagram 비즈니스 로그인으로 API 설정"**.
4. 1단계 **"Instagram 계정 추가"** → 인스타 로그인.
5. 2단계 **"액세스 토큰 생성"** → 계정 옆 **토큰 생성** → 인스타 로그인 → 토큰 복사(60일짜리 장기 토큰). 같은 화면에 **Instagram 계정 ID**(숫자)가 표시된다.
   - 앱이 "개발 모드"여도 이 화면에서 추가한 본인 계정으로는 게시가 된다. 앱 심사는 다른 사람 계정을 다룰 때만 필요하다.

### C. 설정 파일 작성
```bash
mkdir -p ~/.config/insta-agent && cp ~/insta-cards/tools/config.example.json ~/.config/insta-agent/config.json && open -e ~/.config/insta-agent/config.json
```
`ig_user_id`(계정 ID), `access_token`(토큰)을 채우고, `token_updated_at`을 오늘 날짜로 바꾼다.
`handle` 키를 추가하면(`"handle": "@내계정"`) 카드 푸터에 찍힌다. 저장 후 확인:
```bash
cd ~/insta-cards && node tools/post_instagram.mjs --check
```
`username` 이 내 계정으로 나오면 성공. 토큰은 30일 넘으면 게시 때 자동 갱신된다.

### D. GitHub 저장소 + Pages (한 번만)
```bash
cd ~/insta-cards && git init -b main && git add -A && git commit -m "init" && gh repo create ukiahptc/insta-cards --public --source . --push
```
```bash
gh api -X POST repos/ukiahptc/insta-cards/pages -f 'source[branch]=main' -f 'source[path]=/'
```
2~3분 뒤 https://ukiahptc.github.io/insta-cards/ 가 열리면 완료.

## 수동 실행
```bash
cd ~/insta-cards && python3 tools/make_cards.py specs/2026-09-05-youth.json
```
```bash
cd ~/insta-cards && git add -A && git commit -m "cards: 2026-09-05-youth" && git push
```
```bash
cd ~/insta-cards && node tools/post_instagram.mjs --dir cards/2026-09-05-youth --caption specs/2026-09-05-youth.caption.txt --dry-run
```
`--dry-run`을 빼면 실제 게시. 결과 마지막 줄에 `permalink`가 나온다.

## 운영 메모
- 게시 중단: 노션 페이지의 `인스타 보류` 체크. 태스크 자체를 끄려면 Claude 앱의 스케줄 태스크에서 비활성화.
- 하루 한 주제당 1건만. `발행 상태`/`인스타 링크`가 채워진 페이지는 다시 올리지 않는다.
- API 한도: 계정당 24시간 100건. 캐러셀 1건 = 1회.
- 이미지 규격: JPEG, 1080×1350(4:5). 캐러셀 전 장은 같은 비율이어야 한다.
