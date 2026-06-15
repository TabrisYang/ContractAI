"""
合約分析器
使用 LLM 分析合約內容：識別類型、摘要、關鍵條款、風險標記
"""
import json
import re
from pathlib import Path
from typing import Optional
from loguru import logger

from .llm.base import BaseLLMProvider, LLMMessage
from ..models.schemas import ContractAnalysis, ContractClause, RiskLevel

ANALYSIS_SYSTEM_PROMPT = """你是一位專業的繁體中文法律合約分析助手，具備台灣法律知識背景。
請分析提供的合約，以嚴格的 JSON 格式回應，不得包含任何 JSON 以外的文字。

回應格式：
{
  "contract_type": "合約類型（如：買賣合約、租賃合約、委任合約、勞動合約、服務合約等）",
  "summary": "合約整體摘要（200字以內，適合非法律背景人士閱讀）",
  "key_clauses": [
    {
      "title": "條款名稱",
      "content": "條款摘要（100字以內）",
      "risk_level": "low/medium/high",
      "notes": "注意事項或補充說明（可選）"
    }
  ],
  "risk_flags": [
    "風險1描述",
    "風險2描述"
  ],
  "recommendations": [
    "建議1",
    "建議2"
  ]
}"""


def _build_analysis_prompt(contract_text: str) -> str:
    # 限制合約長度（避免超出 token 上限）
    max_chars = 6000
    if len(contract_text) > max_chars:
        truncated = contract_text[:max_chars]
        note = f"\n\n[注意：合約已截取前 {max_chars} 字進行分析]"
        text = truncated + note
    else:
        text = contract_text
    return f"請分析以下合約內容：\n\n{text}"


def _parse_llm_response(raw: str, job_id: str, provider_name: str) -> ContractAnalysis:
    """解析 LLM 回傳的 JSON，容錯處理"""
    # 嘗試從回應中擷取 JSON 區塊
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if not json_match:
        logger.warning(f"LLM 回應不含 JSON，使用預設結構。原始回應：{raw[:200]}")
        return ContractAnalysis(
            job_id=job_id,
            contract_type="無法識別",
            summary=raw[:500] if raw else "LLM 未回傳有效分析結果",
            key_clauses=[],
            risk_flags=[],
            recommendations=[],
            analyzed_by=provider_name,
        )

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失敗：{e}，原始：{raw[:300]}")
        return ContractAnalysis(
            job_id=job_id,
            contract_type="解析失敗",
            summary=f"LLM 回應格式錯誤：{str(e)}",
            analyzed_by=provider_name,
        )

    # 解析 key_clauses
    clauses = []
    for c in data.get("key_clauses", []):
        try:
            risk_raw = c.get("risk_level", "low").lower()
            risk = RiskLevel(risk_raw) if risk_raw in ("low", "medium", "high") else RiskLevel.LOW
            clauses.append(ContractClause(
                title=c.get("title", ""),
                content=c.get("content", ""),
                risk_level=risk,
                notes=c.get("notes"),
            ))
        except Exception:
            pass

    return ContractAnalysis(
        job_id=job_id,
        contract_type=data.get("contract_type", "未知"),
        summary=data.get("summary", ""),
        key_clauses=clauses,
        risk_flags=data.get("risk_flags", []),
        recommendations=data.get("recommendations", []),
        analyzed_by=provider_name,
    )


async def analyze_contract(
    job_id: str,
    llm: BaseLLMProvider,
    output_dir: Optional[Path] = None,
) -> ContractAnalysis:
    """
    分析已去識別化的合約

    Args:
        job_id: 任務 ID（用於找到對應的去識別化文字檔）
        llm: LLM 提供者實例
        output_dir: 輸出目錄（預設為 settings.OUTPUT_DIR / job_id）
    """
    from .config import settings

    if output_dir is None:
        output_dir = settings.OUTPUT_DIR / job_id

    # 優先讀去識別化後的純文字版本
    txt_path = output_dir / f"{job_id}_deidentified.txt"
    if not txt_path.exists():
        raise FileNotFoundError(f"找不到合約文字檔：{txt_path}")

    contract_text = txt_path.read_text(encoding="utf-8")
    if not contract_text.strip():
        raise ValueError("合約文字內容為空")

    logger.info(f"開始分析合約 {job_id}，使用 {llm.provider_name}，字數：{len(contract_text)}")

    messages = [
        LLMMessage(role="system", content=ANALYSIS_SYSTEM_PROMPT),
        LLMMessage(role="user", content=_build_analysis_prompt(contract_text)),
    ]

    raw_response = await llm.chat(messages, temperature=0.2, max_tokens=3000)
    analysis = _parse_llm_response(raw_response, job_id, llm.provider_name)

    # 儲存分析結果
    analysis_path = output_dir / f"{job_id}_analysis.json"
    analysis_path.write_text(
        analysis.json(ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"合約分析完成，結果儲存至 {analysis_path}")

    return analysis
