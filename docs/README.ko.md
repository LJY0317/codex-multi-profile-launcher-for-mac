# Codex Multi-Profile Launcher for Mac

공식 `/Applications/ChatGPT.app`을 수정하거나 복제하지 않고, 서로 격리된 두 번째 ChatGPT/Codex 데스크톱 프로필을 실행하는 macOS용 런처입니다.

공식 앱은 기존 계정에 그대로 사용하고, `ChatGPT (2).app`은 별도의 `CODEX_HOME`과 Electron/Chromium 데이터 디렉터리에서 새 계정으로 로그인합니다.

> [!IMPORTANT]
> OpenAI가 제작·보증·지원하는 제품이 아닌 비공식 커뮤니티 프로젝트입니다. ChatGPT와 Codex는 OpenAI의 상표입니다.

## 생성되는 항목

| 용도 | 경로 |
| --- | --- |
| 두 번째 런처 | `~/Applications/ChatGPT (2).app` |
| 두 번째 Codex home | `~/.codex-account2` |
| 두 번째 데스크톱 프로필 | `~/Library/Application Support/Codex-Account2` |
| 설치 manifest | `~/Library/Application Support/CodexMultiProfileLauncher/install-manifest.json` |

기본 프로필의 인증 파일을 읽거나 복사·이동·삭제하지 않습니다. 공식 앱을 수정·복제·재서명하지 않습니다.

## 요구 사항

- Apple Silicon 또는 Intel Mac
- `/Applications/ChatGPT.app`에 설치된 공식 앱
- `python3` 명령으로 실행 가능한 Python 3

OpenAI는 이 런처 방식을 공식 다중 계정 기능으로 문서화하지 않았습니다. 향후 공식 앱 업데이트로 동작이 달라질 수 있습니다.

## 설치와 실행

```sh
./scripts/install.sh
open "$HOME/Applications/ChatGPT (2).app"
```

새 창에서 두 번째 계정으로 직접 로그인하세요. `auth.json`, 쿠키 또는 기존 프로필을 복사하지 마세요.

```sh
./scripts/status.sh
./scripts/launch.sh
```

실행 중인 실제 창이나 Dock 표시는 공식 앱의 이름과 아이콘으로 보일 수 있습니다.

## 제거와 원복

먼저 두 번째 프로필을 종료합니다. 삭제 예정 항목만 확인하려면:

```sh
./scripts/uninstall.sh
```

두 번째 로그인과 로컬 대화를 포함한 추가 프로필 데이터를 모두 제거하려면:

```sh
./scripts/uninstall.sh --yes
```

제거 프로그램은 manifest에 기록된 고정 경로만 허용합니다. symlink, 바뀐 디렉터리, 기본 프로필의 보호 경로, mount된 하위 경로, 실행 중인 프로필은 삭제를 거부합니다. 프로젝트 소스와 사용자가 Dock에 직접 고정한 항목은 자동으로 제거하지 않습니다.

## 격리 범위와 제한

`CODEX_HOME`과 Electron/Chromium user-data는 분리됩니다. Keychain, URL handler, 권한, 캐시, updater, helper/service까지 운영체제 수준에서 완전히 격리된다고 보장하지는 않습니다. 검증되기 전에는 Computer Use를 한 번에 한 프로필에서 사용하고, Remote는 각 계정에서 새로 연결하는 것을 권장합니다.

두 프로필의 `CODEX_HOME` 또는 user-data 경로를 공유하거나 symlink로 연결하지 마세요. 계정 사이에서 작업을 이어갈 때는 프로젝트 파일과 인계 문서를 공유하고, 동시 작업은 별도 Git worktree를 사용하는 편이 안전합니다.

런처는 Homebrew 및 macOS의 표준 명령 경로에서 `python3`를 찾습니다. Python 3가 제거되면 다시 설치하거나, 현재 Python 3로 `src/codex_profile.py launch`를 실행하세요.

## 개발 및 검증

```sh
python3 -m unittest discover -s tests -v
for script in scripts/*.sh; do sh -n "$script"; done
python3 -m py_compile src/codex_profile.py tests/test_safety.py
```

보안 문제는 [SECURITY.md](../SECURITY.md), 기여 방법은 [CONTRIBUTING.md](../CONTRIBUTING.md)를 확인하세요.

## 라이선스 및 참고

MIT 라이선스입니다. 구현 아이디어를 검토한 커뮤니티 프로젝트는 영어 [README](../README.md#prior-art)에 기록했습니다. 외부 프로젝트의 소스 코드는 포함하지 않았습니다.
