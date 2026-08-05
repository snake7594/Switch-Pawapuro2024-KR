"""Create small, indented JSON reports for human review.

The machine JSON contains one record per extracted string and is intentionally
compact.  This report keeps the original files untouched and presents counts,
structural groups, representative examples, and only the exceptional records.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORDS = ROOT / "main_patch" / "main_strings_ko_review.json"
DEFAULT_REPORT = ROOT / "main_patch" / "main_target_review.json"
DEFAULT_OUT = ROOT / "main_patch" / "main_target_review_human.json"
DEFAULT_NONLOC_OUT = ROOT / "main_patch" / "main_non_localization_human.json"
DEFAULT_MANUAL_OUT = ROOT / "main_patch" / "main_manual_review_human.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def pair(rec: dict) -> dict:
    """The fields useful for a person comparing original and candidate text."""
    return {
        "offset": rec["offset"],
        "text": rec["text"],
        "korean_candidate": rec.get("korean", ""),
        "capacity": rec.get("capacity"),
        "target_status": rec.get("target_status"),
        "semantic_role": rec.get("semantic_role"),
        "target_confidence": rec.get("target_confidence"),
        "review_flags": rec.get("review_flags", []),
    }


def samples(records: list[dict], limit: int = 3) -> list[dict]:
    if len(records) <= limit * 2:
        chosen = records
    else:
        chosen = records[:limit] + records[-limit:]
    return [pair(rec) for rec in chosen]


def unknown_group(text: str) -> str:
    """Give repetitive achievement/stat strings a readable review bucket."""
    if text.startswith("ペナント：アイテム使用回数"):
        return "ペナント / 아이템 사용 횟수 키"
    if text.startswith("ペナント："):
        return "ペナント / 기록·평가 키"
    if text.startswith("マイライフ：選択した進行"):
        return "マイライフ / RESULT 진행 키"
    if text.startswith("マイライフ："):
        return "マイライフ / 도전·아이템 키"
    if text.startswith("サクセス"):
        return "サクセス / 구단·에필로그 키"
    if text.startswith("難易度"):
        return "난이도 / 달성 조건 키"
    if text.startswith("選手テーマ"):
        return "선수 테마 키"
    if text.startswith("ブラバン"):
        return "브라스밴드 곡 키"
    if text.startswith("ホームランアタック"):
        return "홈런 어택 통계 키"
    if text.startswith("オンライン"):
        return "온라인 통신 통계 키"
    if text.startswith("栄冠ナイン"):
        return "栄冠ナイン 통계 키"
    if text.startswith("ペナント"):
        return "ペナント 기타 키"
    if text.startswith("パワプロ"):
        return "파워프로 모드 키"
    if text.startswith("SD_"):
        return "SD 리소스 키"
    if text.startswith("Ｆ普通"):
        return "실행 옵션 키"
    return "기타 미분류 문자열"


def block_summary(records: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        sid = rec.get("structure_id")
        if sid and sid.startswith("input_filter_"):
            grouped[sid].append(rec)
    out: list[dict] = []
    for sid in sorted(grouped):
        rows = grouped[sid]
        alphabet = [r for r in rows if r.get("semantic_role") == "input_character_alphabet"]
        filters = [r for r in rows if r.get("semantic_role") == "profanity_filter_entry"]
        labels = [r for r in rows if r.get("semantic_role") == "input_filter_ui_label"]
        out.append({
            "block_id": sid,
            "alphabet_entries": len(alphabet),
            "filter_entries": len(filters),
            "ui_label_entries": len(labels),
            "alphabet_samples": [r["text"] for r in alphabet[:3] + alphabet[-3:]],
            "filter_samples": [r["text"] for r in filters[:3] + filters[-3:]],
            "ui_labels": sorted({r["text"] for r in labels}),
            "judgment": "게임 입력 문자/금칙어 비교용 런타임 사전이므로 원문 보존",
        })
    return out


def status_group(records: list[dict], status: str) -> dict:
    rows = [r for r in records if r.get("target_status") == status]
    return {
        "target_status": status,
        "count": len(rows),
        "samples": samples(rows),
    }


def make_reports(records_path: Path, report_path: Path, out_path: Path,
                 nonloc_path: Path, manual_path: Path) -> None:
    records_obj = load(records_path)
    records = records_obj["strings"]
    report = load(report_path)

    status_counts = Counter(r.get("target_status") for r in records)
    decision_counts = Counter(r.get("localization_decision") for r in records)
    untranslated = [r for r in records if r.get("translation_source") == "untranslated"]
    preserved = [r for r in records if r.get("preserve_original")]
    manual = [r for r in records if r.get("localization_target") == "review"]
    format_issues = [r for r in records if "format_token_mismatch" in r.get("review_flags", [])]
    names = [r for r in records if r.get("target_status") == "name_transliteration_review"]
    menus = [r for r in records if r.get("target_status") == "translate_fixed_menu"]

    unknown = [r for r in records if r.get("target_status") == "review_unknown"]
    unknown_buckets: dict[str, list[dict]] = defaultdict(list)
    for rec in unknown:
        unknown_buckets[unknown_group(rec["text"])].append(rec)
    unknown_groups = [
        {
            "group": key,
            "count": len(rows),
            "judgment": "내부 통계/업적 키일 가능성이 높지만, 화면 표시 여부를 포인터만으로 확정할 수 없어 수동 확인",
            "samples": samples(rows, 2),
        }
        for key, rows in sorted(unknown_buckets.items(), key=lambda item: (-len(item[1]), item[0]))
    ]

    preserve_groups = [
        {
            "target_status": "preserve_internal_dictionary",
            "count": status_counts["preserve_internal_dictionary"],
            "roles": {
                "input_character_alphabet": sum(r.get("semantic_role") == "input_character_alphabet" for r in preserved),
                "profanity_filter_entry": sum(r.get("semantic_role") == "profanity_filter_entry" for r in preserved),
            },
            "judgment": "표시 대사가 아니라 이름 입력/금칙어 판정에 쓰이는 키. 한국어로 치환하면 런타임 매칭이 깨질 수 있으므로 원문 보존",
            "blocks": block_summary(records),
        },
        {
            "target_status": "preserve_debug_or_binary",
            "count": status_counts["preserve_debug_or_binary"],
            "judgment": "UTF-8 스캐너가 데이터/디버그 영역을 문자열로 오인한 항목",
            "entries": [pair(r) for r in preserved if r.get("target_status") == "preserve_debug_or_binary"],
        },
    ]

    summary = {
        "format": 2,
        "title": "Powerful Pro Baseball 2026 main 문자열 한글화 검토 요약",
        "purpose": "전체 추출 JSON 대신 사람이 판단할 수 있도록 구조·예외·대표 샘플만 정리한 파일",
        "machine_files": {
            "all_records": str(records_path),
            "full_report": str(report_path),
            "full_non_localization_list": "main_patch\\main_non_localization_candidates_refined.json",
            "full_manual_review_list": "main_patch\\main_manual_review_all.json",
        },
        "how_to_read": {
            "translate": "게임 화면에 표시될 가능성이 있어 한글화 대상",
            "preserve_original": "원문 바이트를 유지해야 하는 런타임 사전 또는 바이너리 오탐",
            "manual_review": "자동으로 화면 표시 여부를 확정하지 않은 항목",
            "target_status": "세 단계보다 구체적인 판단 근거",
        },
        "overview": {
            "total_strings": len(records),
            "translated_in_current_json": len(records) - len(untranslated),
            "untranslated_in_current_json": len(untranslated),
            "decision_counts": dict(decision_counts),
            "status_counts": dict(status_counts),
        },
        "preserve_original": {
            "total": len(preserved),
            "groups": preserve_groups,
        },
        "translate_but_not_dialogue": {
            "name_transliteration_review": {
                "count": len(names),
                "judgment": "고정 이름표는 대사가 아니지만 한국어 독음으로 바꿔야 할 수 있음. 기계 번역 대신 이름 독음 검토",
                "samples": samples(names, 8),
            },
            "translate_fixed_menu": {
                "count": len(menus),
                "judgment": "고정 메뉴 테이블이므로 번역 대상",
                "samples": samples(menus, 5),
            },
        },
        "manual_review": {
            "total": len(manual) + len(format_issues),
            "unknown_count": len(unknown),
            "format_issue_count": len(format_issues),
            "unknown_groups": unknown_groups,
            "format_issues": [pair(r) | {
                "format_signature_source": r.get("format_signature_source"),
                "format_signature_korean": r.get("format_signature_korean"),
                "format_signature_game": r.get("format_signature_game"),
                "translation_sentinels": r.get("translation_sentinels", []),
            } for r in format_issues],
        },
        "quality_checks": {
            "dictionary_blocks": len(report.get("dictionary_blocks", [])),
            "input_filter_alphabet_entries": report["counts"].get("input_filter_alphabet_entries", 0),
            "input_filter_entries": report["counts"].get("input_filter_entries", 0),
            "control_byte_entries": report["counts"].get("control_byte_entries", 0),
            "format_token_issues": len(format_issues),
            "nso_header_has_dialogue_semantic_flag": False,
        },
        "limitations": [
            "NSO 헤더에는 대사/비대사 의미 플래그가 없으므로 포인터만으로 화면 표시 여부를 확정할 수 없음",
            "이름표는 대사가 아니어도 실제 화면에 표시되므로 preserve가 아니라 독음 검토로 분리",
            "control_bytes가 있는 문자열은 보이는 글자만 번역하고 제어 바이트는 그대로 유지",
        ],
    }

    nonloc = {
        "format": 2,
        "title": "한글화 제외 후보 요약",
        "count": len(preserved),
        "judgment": "보존 여부를 사람이 빠르게 확인하기 위한 구조별 요약. 전체 항목은 machine_files의 전체 목록 참조",
        "groups": preserve_groups,
    }
    manual_out = {
        "format": 2,
        "title": "수동 검토 항목 요약",
        "count": len(manual) + len(format_issues),
        "format_issues": summary["manual_review"]["format_issues"],
        "unknown_groups": unknown_groups,
        "note": "각 그룹은 대표 샘플만 포함하며 전체 1,044건은 main_manual_review_all.json에 있음",
    }

    for path, payload in ((out_path, summary), (nonloc_path, nonloc), (manual_path, manual_out)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{path}: {path.stat().st_size} bytes")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--nonloc-out", type=Path, default=DEFAULT_NONLOC_OUT)
    ap.add_argument("--manual-out", type=Path, default=DEFAULT_MANUAL_OUT)
    args = ap.parse_args()
    make_reports(args.records, args.report, args.out, args.nonloc_out, args.manual_out)


if __name__ == "__main__":
    main()
