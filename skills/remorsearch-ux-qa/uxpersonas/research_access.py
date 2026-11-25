"""Explicit local research references; no collection, copies, cleanup or new grades."""
from contextlib import contextmanager
from pathlib import Path
import re
import stat

from uxresearch.canonical import EngineError, digest, loads
from uxresearch.ledger import Run
from uxresearch.storage import inspection_lock, read_bytes, read_json, safe_path
from . import workspace


def refuse(code, reason):
    workspace.stop(code, reason, "호스트가 승인된 연구 위치와 현재 근거를 확인합니다. 원본·기존 결과를 보존하며 자동 재수집·재실행하지 않습니다.")


def roots_for(values, *, work, source, library):
    values = [] if values is None else list(values)
    if len(values) > 4:
        refuse("research_scope", "한 실행에서 검토할 연구 위치는 최대 4개입니다.")
    roots = []
    boundaries = [safe_path(value) for value in (work, source, library)]
    for value in values:
        root = safe_path(value)
        if (root in roots or any(root.is_relative_to(other) or other.is_relative_to(root)
                                 for other in [*boundaries, *roots])):
            refuse("research_scope", "연구·원본·페르소나·실행 폴더는 서로 분리된 위치여야 합니다.")
        if not root.is_dir() or root.stat().st_mode & 0o077:
            refuse("research_permissions", "기존 비공개 연구 폴더만 읽습니다. 폴더를 만들거나 권한을 바꾸지 않습니다.")
        roots.append(root)
    return sorted(map(str, roots))


def inspect_files(root):
    """Read only fixed consumer metadata and committed gate dependencies, never pages."""
    total = 0
    def read(name):
        nonlocal total
        path = safe_path(root / name, root)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            refuse("research_file", "연구 입력은 링크가 없는 일반 파일이어야 합니다.")
        raw = read_bytes(path, private=True)
        total += len(raw)
        if total > workspace.MAX_TOTAL:
            refuse("research_size", "현재 연구 검증 입력이 읽기 한도를 넘었습니다.")
        if workspace.SECRET.search(raw):
            refuse("sensitive_content", "연구 검증 입력에 비밀 형식이 있어 읽기를 중단했습니다.")
        return raw
    required = ("engine.lock", "state.lock", "engine-state.json", "run.json",
                "routes.json", "hosts.json", "access-ledger.jsonl", "bundle.json", "gate.json")
    raw = {name: read(name) for name in required}
    for name in ("brief.json", "agent-tokens.json", "search-ledger.jsonl", "gate_failed.json"):
        path = root / name
        if path.exists() or path.is_symlink():
            read(name)
    state = loads(raw["engine-state.json"])
    outputs = state.get("outputs", {})
    for name in ("bundle.json", "gate.json", "merge_receipt.json", "query_log.json",
                 "expansion_log.json", "gate_receipt.json"):
        if name == "gate_receipt.json" and name not in outputs:
            continue
        entry = outputs.get(name, {})
        generation = entry.get("generation_path", "")
        if (entry.get("file") != name or
                not re.fullmatch(r"\.engine/[0-9a-f]{64}/" + re.escape(name), generation)):
            refuse("research_snapshot", "연구 snapshot 경로가 현재 검증 형식과 다릅니다.")
        read(generation)


class ReferenceScope:
    """An additional guard; existing Library/gate validation still decides usability."""
    def __init__(self, prepared, roots):
        self.prepared = prepared
        self.roots = set(roots)
        self.used = set()

    def __call__(self, record):
        if record.get("status") != "active":
            refuse("persona_retired", "폐기된 페르소나는 현재 실행에 재사용할 수 없습니다.")
        if record.get("basis") != "synthetic":
            refuse("persona_scope", "저장된 합성 페르소나만 이 로컬 경로에 연결합니다.")
        provenance = record.get("provenance", {})
        mode = provenance.get("mode")
        if mode == "prd_hypothesis":
            if provenance != {"mode": "prd_hypothesis", "claim_ids": []} or "research_scenarios" in record.get("profile", {}):
                refuse("persona_scope", "PRD 가설에 검토하지 않은 연구 참조가 있습니다.")
        elif mode == "gated_research":
            binding = provenance.get("research", {})
            # Compare lexical paths first; do not inspect unapproved reference targets.
            root_name = binding.get("run")
            if root_name not in self.roots:
                refuse("persona_scope", "저장된 페르소나의 연구 위치를 호스트가 명시적으로 검토해야 합니다.")
            if (binding.get("bundle") != str(Path(root_name) / "bundle.json")
                    or binding.get("gate") != str(Path(root_name) / "gate.json")):
                refuse("research_scope", "연구 참조가 검토한 폴더의 고정 bundle·gate와 다릅니다.")
        else:
            refuse("persona_scope", "지원하지 않는 페르소나 근거 형식입니다.")
        prd = safe_path(record["context"]["prd_path"])
        source = safe_path(self.prepared["source"])
        if not prd.is_relative_to(source) or prd.relative_to(source).as_posix() not in self.prepared["inputs"]:
            refuse("persona_scope", "페르소나 PRD가 검토한 제품 입력 밖에 있습니다.")
        if mode == "gated_research":
            root = safe_path(root_name)
            if not root.is_dir() or root.stat().st_mode & 0o077:
                refuse("research_permissions", "연구 폴더가 없거나 비공개 경계가 바뀌었습니다.")
            inspect_files(root)
            self.used.add(root_name)


class ResearchView(Run):
    """Existing policy/gate consumer with inspection-only ledger access.

    Run construction normally purges old page caches. Inspection deliberately does
    not; fresh() still enforces source/capture retention and current gate rules.
    """
    def purge_pages(self):
        return 0

    def _refuse_write(self, *args, **kwargs):
        raise EngineError("research_read_only", "Research inspection cannot collect, update or remove data.")

    require_open = log = save_page = close = store_robots = _strip_ledger_urls = _delete_private = _refuse_write

    @contextmanager
    def _state(self):
        with inspection_lock(self.path / "state.lock"):
            state = read_json(self.path / "hosts.json", private=True)
            before = digest(state)
            yield state
            if digest(state) != before:
                self._refuse_write()
