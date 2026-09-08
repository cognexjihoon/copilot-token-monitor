# Copilot Usage Monitor

GitHub Copilot의 월간 AI-credit 사용량을 시스템 트레이에서 확인하는 상주 프로그램입니다. 영업일 기준 사용 페이스를 계산해 아래 상태를 트레이 아이콘 색으로 보여주고, 상세 창에서 누적 사용량 추이 그래프를 확인할 수 있습니다.

| 상태 | 의미 |
| :-: | --- |
| 🟢 여유 | 페이스 대비 80% 이하로 사용 중 |
| 🔵 적정 | 페이스 대비 80~105% 사용 중 |
| 🟡 주의 | 페이스 대비 105~120% 사용 중 |
| 🟠 위험 | 페이스 대비 120% 초과로 사용 중 |
| 🔴 임박 | 쿼터의 90% 이상 사용 (페이스와 무관) |
| 💀 초과 | 쿼터를 다 소진 - 트레이 아이콘도 숫자 대신 해골로 표시 |

## 왜 이렇게 동작하나

GitHub의 청구 API는 조직 관리자만 다른 멤버의 사용량을 조회할 수 있습니다. 그래서 이 프로그램은 로그인 세션으로 `github.com/settings/copilot/features` 페이지를 주기적으로 읽어와 "used / quota" 숫자를 직접 파싱합니다(`scrape_client.py`). GitHub이 페이지 구조를 바꾸면 깨질 수 있는 방식이라, 일시적인 파싱/네트워크 실패는 몇 차례 자동 재시도하고, 그래도 실패하면(또는 로그인 세션이 만료되면) 트레이에 즉시 오류로 표시합니다.

## 요구 사항

- Python 3.11 이상
- Windows (시스템 트레이 상주 + DPAPI로 세션 쿠키 암호화 저장을 전제로 설계됨. Qt 기반이라 macOS/Linux에서도 실행은 되지만 검증된 대상은 아닙니다.)
- Copilot이 활성화된 GitHub 계정

## 설치

```powershell
git clone https://github.com/cognexjihoon/copilot-token-monitor.git
cd copilot-token-monitor
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 실행

```powershell
python main.py
```

최초 실행 시 설정 창이 자동으로 뜹니다.

1. **GitHub 로그인** 버튼 클릭 → 내장 브라우저로 평소처럼 로그인(회사 SSO/2FA 포함) → 로그인되면 세션 쿠키가 자동으로 캡처됩니다.
2. **확인 주기**(분)를 원하는 값으로 설정합니다.
3. **연결 테스트**로 사용량이 정상 조회되는지 확인한 뒤 OK를 누릅니다.

이후에는 시스템 트레이 아이콘에 사용량 퍼센트가 표시되고, 설정한 주기마다 자동으로 새로고침됩니다. 트레이 아이콘을 우클릭하면 상세 보기 / 지금 새로고침 / 설정 / 종료 메뉴가 나옵니다.

설정과 사용량 캐시는 `%APPDATA%\CopilotUsageMonitor\`에 저장됩니다(`config.json`, `usage_cache.json`). 세션 쿠키는 Windows DPAPI로 암호화되어 저장됩니다.

## 테스트

```powershell
pytest
```

## 라이선스

MIT License. [LICENSE](LICENSE) 참고.
