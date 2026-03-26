# jakal-flow (한국어)

`jakal-flow`는 격리된 워크스페이스 안에서 여러 저장소를 관리하고, Codex CLI 기반 개선 루프를 반복 실행할 수 있게 설계된 Python CLI입니다.

- OpenAI/Codex 클라우드 모델
- OpenRouter/OpenCDK 같은 OpenAI 호환 제공자
- Codex OSS 모드 및 로컬 OpenAI 호환 서버

를 포함한 다양한 실행 구성을 지원합니다.

## 흐름도

![jakal-flow 플로우 차트 (KO)](assets/readme-flow-ko.svg)

영문 문서는 [README.md](README.md)를 참고하세요.

## 프로젝트 레이아웃

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
      metadata.json
      project_config.json
```

## 설치

```bash
python -m pip install -e .
```

## 자주 쓰는 명령

관리 저장소 초기화:

```bash
python -m jakal_flow init-repo \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest"
```

개선 루프 실행:

```bash
python -m jakal_flow run \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 2
```

기존 관리 저장소 재개:

```bash
python -m jakal_flow resume \
  --repo-url https://github.com/example/project.git \
  --branch main \
  --workspace-root .jakal-flow-workspace \
  --model gpt-5.4 \
  --effort high \
  --approval-mode never \
  --sandbox-mode workspace-write \
  --test-cmd "python -m pytest" \
  --max-blocks 1
```

## 데스크톱 UI

데스크톱 UI는 `desktop/`(React + Tauri)에 있습니다.

개발 실행:

```bash
cd desktop
npm.cmd install
npm.cmd run tauri:dev
```

## 참고

- 저장소별로 `docs/`, `state/`, `memory/`, `logs/`, `reports/`를 분리해 추적성과 롤백 안전성을 유지합니다.
- 공유 링크는 읽기 전용 모니터링 용도이며, 로컬 공유 서버 또는 터널을 통해 제공합니다.
