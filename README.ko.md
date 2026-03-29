# jakal-flow

Codex 계열 작업을 위한 추적 가능한 멀티 리포지토리 자동화 도구입니다.

`jakal-flow`는 관리 대상 저장소마다 별도의 워크스페이스를 만들고, 계획서, 로그, 리포트, 메모리, 롤백 상태를 프로젝트별로 분리해서 저장합니다. 기본 진입점은 Python CLI이며, React + Tauri 데스크톱 셸도 같은 백엔드를 그대로 사용합니다.

- English guide: [README.md](README.md)

## 요구 사항

- Python 3.11+
- `PATH`에 Codex CLI
- 데스크톱 셸이 필요하면 Node.js 20+, Rust, Tauri 사전 요구 사항

## 설치

```bash
python -m pip install -e .
```

설치되는 진입점:

- `jakal-flow`
- `jakal-flow-ui-bridge`

현재 체크아웃 기준 CLI 표면 확인:

```bash
$env:PYTHONPATH='src'; python -m jakal_flow --help
```

## 빠른 시작

런타임 설정 파일을 만듭니다.

```toml
[runtime]
model_provider = "openai"
model = "gpt-5.4"
effort = "high"
approval_mode = "never"
sandbox_mode = "workspace-write"
test_cmd = "python -m pytest"
max_blocks = 2
```

관리할 저장소를 초기화합니다.

```bash
jakal-flow init-repo \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --config .jakal-flow.runtime.toml
```

작업을 실행합니다.

```bash
jakal-flow run \
  --repo-url https://github.com/Ahnd6474/lit.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --config .jakal-flow.runtime.toml
```

자주 쓰는 후속 명령:

```bash
jakal-flow resume --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace --config .jakal-flow.runtime.toml
jakal-flow status --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
jakal-flow report --repo-url https://github.com/Ahnd6474/lit.git --branch main --workspace-root .jakal-flow-workspace
```

## 워크스페이스 구조

관리 대상 저장소마다 아래처럼 독립된 하위 트리를 가집니다.

```text
workspace_root/
  projects/
    <repo_slug>/
      repo/
      docs/
      memory/
      logs/
      reports/
      state/
```

이 구조 덕분에 멀티 리포지토리 이력과 추적 정보가 프로젝트별로 분리됩니다.

## 데스크톱 UI

데스크톱 앱은 같은 Python 백엔드 위에 올라가는 React + Tauri 셸입니다.

개발 실행:

```bash
cd desktop
npm install
npm run tauri:dev
```

빌드:

```bash
cd desktop
npm run tauri:build
```
