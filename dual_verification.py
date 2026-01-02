"""
dual_verification.py - 双模型验证模块

实现三层验证架构：
1. Layer 1: 关系识别 (主模型)
2. Layer 2: 找碴验证 (Devil's Advocate)
3. Layer 3: 双模型交叉验证 (可选)

验证结果分类：
- VERIFIED: 双模型一致，通过找碴验证
- NEEDS_REVIEW: 存在分歧或边界情况，需人工复核
- REJECTED: 验证失败，不推荐执行
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class VerificationStatus(Enum):
    """验证状态"""
    VERIFIED = "verified"           # 验证通过
    NEEDS_REVIEW = "needs_review"   # 需人工复核
    REJECTED = "rejected"           # 验证失败


@dataclass
class DevilsAdvocateResult:
    """找碴验证结果"""
    risks_found: List[str] = field(default_factory=list)
    edge_cases: List[str] = field(default_factory=list)
    settlement_issues: List[str] = field(default_factory=list)
    risk_level: str = "low"  # low, medium, high
    recommendation: str = ""
    raw_response: str = ""


@dataclass
class SecondOpinionResult:
    """第二意见结果"""
    agrees: bool = True
    relationship: str = ""
    confidence: float = 0.0
    disagreement_reason: str = ""
    raw_response: str = ""


@dataclass
class VerificationResult:
    """完整验证结果"""
    status: VerificationStatus
    primary_analysis: Dict
    devils_advocate: Optional[DevilsAdvocateResult] = None
    second_opinion: Optional[SecondOpinionResult] = None

    # 综合评估
    overall_confidence: float = 0.0
    human_review_reasons: List[str] = field(default_factory=list)
    execution_recommendation: str = ""

    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "overall_confidence": self.overall_confidence,
            "human_review_reasons": self.human_review_reasons,
            "execution_recommendation": self.execution_recommendation,
            "primary_analysis": self.primary_analysis,
            "devils_advocate": {
                "risks_found": self.devils_advocate.risks_found if self.devils_advocate else [],
                "edge_cases": self.devils_advocate.edge_cases if self.devils_advocate else [],
                "settlement_issues": self.devils_advocate.settlement_issues if self.devils_advocate else [],
                "risk_level": self.devils_advocate.risk_level if self.devils_advocate else "unknown",
            } if self.devils_advocate else None,
            "second_opinion": {
                "agrees": self.second_opinion.agrees if self.second_opinion else None,
                "relationship": self.second_opinion.relationship if self.second_opinion else "",
                "confidence": self.second_opinion.confidence if self.second_opinion else 0.0,
                "disagreement_reason": self.second_opinion.disagreement_reason if self.second_opinion else "",
            } if self.second_opinion else None,
        }


class DualModelVerifier:
    """
    双模型验证器

    使用两个独立的 LLM 模型进行交叉验证：
    1. 主模型：进行关系分析
    2. 验证模型：进行找碴验证 + 第二意见

    配置示例：
        verifier = DualModelVerifier(
            primary_client=deepseek_client,
            verification_client=qwen_client  # 通过 SiliconFlow
        )
    """

    def __init__(
        self,
        primary_client: Any = None,
        verification_client: Any = None,
        enable_devils_advocate: bool = True,
        enable_second_opinion: bool = True,
        confidence_threshold: float = 0.8
    ):
        """
        初始化双模型验证器

        Args:
            primary_client: 主模型客户端（用于关系分析）
            verification_client: 验证模型客户端（用于找碴和第二意见）
            enable_devils_advocate: 是否启用找碴验证
            enable_second_opinion: 是否启用第二意见
            confidence_threshold: 置信度阈值
        """
        self.primary_client = primary_client
        self.verification_client = verification_client or primary_client
        self.enable_devils_advocate = enable_devils_advocate
        self.enable_second_opinion = enable_second_opinion
        self.confidence_threshold = confidence_threshold

        # 导入 prompts（延迟导入避免循环依赖）
        self._prompts_loaded = False
        self._devils_advocate_prompt = None
        self._second_opinion_prompt = None

    def _load_prompts(self):
        """延迟加载 prompts"""
        if self._prompts_loaded:
            return

        try:
            from prompts import (
                format_devils_advocate_prompt,
                format_second_opinion_prompt,
                DEVILS_ADVOCATE_PROMPT_LITE
            )
            self._format_devils_advocate = format_devils_advocate_prompt
            self._format_second_opinion = format_second_opinion_prompt
            self._prompts_loaded = True
        except ImportError as e:
            logger.warning(f"无法导入 prompts 模块: {e}")
            self._prompts_loaded = False

    def verify(
        self,
        market_a: Any,
        market_b: Any,
        primary_analysis: Dict
    ) -> VerificationResult:
        """
        执行完整的双模型验证

        Args:
            market_a: 市场A
            market_b: 市场B
            primary_analysis: 主模型的关系分析结果

        Returns:
            VerificationResult 包含完整验证结果
        """
        self._load_prompts()

        human_review_reasons = []
        devils_result = None
        second_opinion_result = None

        # 检查主分析置信度
        primary_confidence = primary_analysis.get("confidence", 0.0)
        relationship = primary_analysis.get("relationship", "UNRELATED")

        if primary_confidence < self.confidence_threshold:
            human_review_reasons.append(
                f"主模型置信度较低 ({primary_confidence:.2f} < {self.confidence_threshold})"
            )

        # 如果关系是 UNRELATED，跳过验证
        if relationship == "UNRELATED":
            return VerificationResult(
                status=VerificationStatus.REJECTED,
                primary_analysis=primary_analysis,
                overall_confidence=primary_confidence,
                human_review_reasons=["无套利关系"],
                execution_recommendation="无需执行 - 市场间无逻辑关系"
            )

        # Layer 2: 找碴验证
        if self.enable_devils_advocate and self.verification_client:
            devils_result = self._run_devils_advocate(
                market_a, market_b, relationship
            )

            if devils_result and devils_result.risk_level == "high":
                human_review_reasons.append(f"找碴验证发现高风险: {', '.join(devils_result.risks_found[:3])}")
            elif devils_result and devils_result.settlement_issues:
                human_review_reasons.append(f"结算规则可能有差异: {', '.join(devils_result.settlement_issues[:2])}")

        # Layer 3: 双模型交叉验证
        if self.enable_second_opinion and self.verification_client:
            second_opinion_result = self._get_second_opinion(
                market_a, market_b, primary_analysis
            )

            if second_opinion_result and not second_opinion_result.agrees:
                human_review_reasons.append(
                    f"双模型意见分歧: {second_opinion_result.disagreement_reason}"
                )

        # 综合评估
        status, overall_confidence, recommendation = self._evaluate_results(
            primary_analysis,
            devils_result,
            second_opinion_result,
            human_review_reasons
        )

        return VerificationResult(
            status=status,
            primary_analysis=primary_analysis,
            devils_advocate=devils_result,
            second_opinion=second_opinion_result,
            overall_confidence=overall_confidence,
            human_review_reasons=human_review_reasons,
            execution_recommendation=recommendation
        )

    def _run_devils_advocate(
        self,
        market_a: Any,
        market_b: Any,
        relationship: str
    ) -> Optional[DevilsAdvocateResult]:
        """
        运行找碴验证

        Prompt: "假设A发生但B没结算为YES，有哪些可能的情况？"
        """
        if not self._prompts_loaded:
            return None

        try:
            # 构建市场信息
            market_a_info = {
                "question": getattr(market_a, 'question', str(market_a)),
                "description": getattr(market_a, 'description', ''),
                "yes_price": getattr(market_a, 'yes_price', 0.5),
                "end_date": getattr(market_a, 'end_date', 'N/A'),
            }
            market_b_info = {
                "question": getattr(market_b, 'question', str(market_b)),
                "description": getattr(market_b, 'description', ''),
                "yes_price": getattr(market_b, 'yes_price', 0.5),
                "end_date": getattr(market_b, 'end_date', 'N/A'),
            }

            prompt = self._format_devils_advocate(
                market_a_info, market_b_info, relationship, lite=True
            )

            response = self.verification_client.chat(prompt)
            content = response.content

            return self._parse_devils_advocate_response(content)

        except Exception as e:
            logger.error(f"找碴验证失败: {e}")
            return None

    def _parse_devils_advocate_response(self, content: str) -> DevilsAdvocateResult:
        """解析找碴验证响应"""
        result = DevilsAdvocateResult(raw_response=content)

        try:
            # 尝试提取 JSON
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
                data = json.loads(json_str.strip())
            elif "{" in content and "}" in content:
                # 尝试找到 JSON 块
                start = content.find("{")
                end = content.rfind("}") + 1
                json_str = content[start:end]
                data = json.loads(json_str)
            else:
                # 无法解析 JSON，从文本中提取信息
                result.risk_level = "medium" if "风险" in content or "risk" in content.lower() else "low"
                return result

            result.risks_found = data.get("risks", data.get("risks_found", []))
            result.edge_cases = data.get("edge_cases", [])
            result.settlement_issues = data.get("settlement_issues", [])
            result.risk_level = data.get("risk_level", "low")
            result.recommendation = data.get("recommendation", "")

        except json.JSONDecodeError:
            logger.warning("无法解析找碴验证响应的 JSON")
            result.risk_level = "medium"  # 默认中等风险

        return result

    def _get_second_opinion(
        self,
        market_a: Any,
        market_b: Any,
        first_analysis: Dict
    ) -> Optional[SecondOpinionResult]:
        """
        获取第二意见（双模型验证）
        """
        if not self._prompts_loaded:
            return None

        try:
            market_a_info = {
                "question": getattr(market_a, 'question', str(market_a)),
                "description": getattr(market_a, 'description', ''),
                "yes_price": getattr(market_a, 'yes_price', 0.5),
            }
            market_b_info = {
                "question": getattr(market_b, 'question', str(market_b)),
                "description": getattr(market_b, 'description', ''),
                "yes_price": getattr(market_b, 'yes_price', 0.5),
            }

            prompt = self._format_second_opinion(
                market_a_info, market_b_info, first_analysis
            )

            response = self.verification_client.chat(prompt)
            content = response.content

            return self._parse_second_opinion_response(content, first_analysis)

        except Exception as e:
            logger.error(f"获取第二意见失败: {e}")
            return None

    def _parse_second_opinion_response(
        self,
        content: str,
        first_analysis: Dict
    ) -> SecondOpinionResult:
        """解析第二意见响应"""
        result = SecondOpinionResult(raw_response=content)

        try:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
                data = json.loads(json_str.strip())
            elif "{" in content and "}" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                json_str = content[start:end]
                data = json.loads(json_str)
            else:
                # 从文本判断是否同意
                content_lower = content.lower()
                result.agrees = "同意" in content or "agree" in content_lower or "正确" in content
                result.relationship = first_analysis.get("relationship", "")
                result.confidence = 0.5
                return result

            result.relationship = data.get("relationship", "").upper()
            result.confidence = data.get("confidence", 0.5)
            result.agrees = data.get("agrees", result.relationship == first_analysis.get("relationship", "").upper())
            result.disagreement_reason = data.get("disagreement_reason", "")

            # 如果 relationship 不同，自动设为不同意
            if result.relationship and result.relationship != first_analysis.get("relationship", "").upper():
                result.agrees = False
                if not result.disagreement_reason:
                    result.disagreement_reason = f"关系判断不同: 主模型={first_analysis.get('relationship')}, 验证模型={result.relationship}"

        except json.JSONDecodeError:
            logger.warning("无法解析第二意见响应的 JSON")
            result.agrees = True  # 默认同意（保守策略）
            result.confidence = 0.5

        return result

    def _evaluate_results(
        self,
        primary_analysis: Dict,
        devils_result: Optional[DevilsAdvocateResult],
        second_opinion: Optional[SecondOpinionResult],
        human_review_reasons: List[str]
    ) -> Tuple[VerificationStatus, float, str]:
        """
        综合评估所有验证结果

        Returns:
            (status, overall_confidence, recommendation)
        """
        primary_confidence = primary_analysis.get("confidence", 0.0)
        relationship = primary_analysis.get("relationship", "UNRELATED")

        # 基础置信度
        overall_confidence = primary_confidence

        # 根据找碴验证调整
        if devils_result:
            if devils_result.risk_level == "high":
                overall_confidence *= 0.5
            elif devils_result.risk_level == "medium":
                overall_confidence *= 0.8

            if devils_result.settlement_issues:
                overall_confidence *= 0.7

        # 根据第二意见调整
        if second_opinion:
            if not second_opinion.agrees:
                overall_confidence *= 0.4
            elif second_opinion.confidence < 0.7:
                overall_confidence *= 0.8

        # 确定状态和建议
        if len(human_review_reasons) >= 2 or overall_confidence < 0.5:
            status = VerificationStatus.NEEDS_REVIEW
            recommendation = "建议人工复核后再决定是否执行"
        elif (devils_result and devils_result.risk_level == "high") or (second_opinion and not second_opinion.agrees):
            status = VerificationStatus.NEEDS_REVIEW
            recommendation = "存在显著风险或分歧，强烈建议人工复核"
        elif overall_confidence >= 0.8 and len(human_review_reasons) == 0:
            status = VerificationStatus.VERIFIED
            recommendation = f"验证通过 - {relationship} 关系确认，可考虑执行"
        else:
            status = VerificationStatus.NEEDS_REVIEW
            recommendation = "部分验证通过，建议人工确认"

        return status, overall_confidence, recommendation


# ============================================================
# 便捷函数
# ============================================================

def create_verifier(
    primary_profile: str = None,
    verification_profile: str = "siliconflow",
    verification_model: str = "Qwen/Qwen2.5-72B-Instruct"
) -> DualModelVerifier:
    """
    创建双模型验证器的便捷函数

    Args:
        primary_profile: 主模型配置名（如 "deepseek"）
        verification_profile: 验证模型配置名（默认 "siliconflow"）
        verification_model: 验证模型名称（默认 Qwen2.5-72B）

    Returns:
        DualModelVerifier 实例
    """
    try:
        from llm_config import get_profile, auto_detect_profile
        from llm_providers import create_llm_client

        # 主模型
        if primary_profile:
            primary = get_profile(primary_profile)
        else:
            primary = auto_detect_profile()

        primary_client = create_llm_client(
            provider="openai_compatible",
            api_key=primary.get_api_key(),
            api_base=primary.api_base,
            model=primary.default_model
        )

        # 验证模型
        verification = get_profile(verification_profile)
        verification_client = create_llm_client(
            provider="openai_compatible",
            api_key=verification.get_api_key(),
            api_base=verification.api_base,
            model=verification_model
        )

        return DualModelVerifier(
            primary_client=primary_client,
            verification_client=verification_client
        )

    except Exception as e:
        logger.warning(f"创建双模型验证器失败: {e}")
        logger.warning("将使用单模型模式")
        return DualModelVerifier(enable_second_opinion=False)


# ============================================================
# 集成到现有分析流程的示例
# ============================================================

def enhanced_analyze_with_verification(
    analyzer,  # LLMAnalyzer 实例
    verifier: DualModelVerifier,
    market_a,
    market_b
) -> Dict:
    """
    增强版分析：主分析 + 双模型验证

    Args:
        analyzer: LLMAnalyzer 实例
        verifier: DualModelVerifier 实例
        market_a, market_b: 市场对

    Returns:
        包含验证结果的完整分析字典
    """
    # 1. 主模型分析
    primary_result = analyzer.analyze(market_a, market_b)

    # 2. 双模型验证
    verification = verifier.verify(market_a, market_b, primary_result)

    # 3. 合并结果
    enhanced_result = {
        **primary_result,
        "verification": verification.to_dict(),
        "verified": verification.status == VerificationStatus.VERIFIED,
        "needs_review": verification.status == VerificationStatus.NEEDS_REVIEW,
        "overall_confidence": verification.overall_confidence,
        "execution_recommendation": verification.execution_recommendation,
    }

    return enhanced_result


# ============================================================
# 测试代码
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("双模型验证模块测试")
    print("=" * 60)

    # 模拟主分析结果
    mock_primary_analysis = {
        "relationship": "IMPLIES_AB",
        "confidence": 0.85,
        "reasoning": "If Trump wins the election, Republicans will control the presidency",
        "edge_cases": ["Third party candidate wins"],
    }

    # 模拟市场
    class MockMarket:
        def __init__(self, question, description="", yes_price=0.5, end_date="2024-11-06"):
            self.question = question
            self.description = description
            self.yes_price = yes_price
            self.end_date = end_date

    market_a = MockMarket(
        "Will Trump win the 2024 presidential election?",
        "Resolves YES if Trump wins",
        0.55
    )
    market_b = MockMarket(
        "Will a Republican win the 2024 presidential election?",
        "Resolves YES if Republican candidate wins",
        0.52
    )

    print(f"\nMarket A: {market_a.question}")
    print(f"Market B: {market_b.question}")
    print(f"\nPrimary Analysis: {mock_primary_analysis['relationship']} (confidence: {mock_primary_analysis['confidence']})")

    # 创建验证器（无实际 LLM 客户端，仅测试逻辑）
    verifier = DualModelVerifier(
        primary_client=None,
        verification_client=None,
        enable_devils_advocate=False,  # 禁用以测试基础逻辑
        enable_second_opinion=False
    )

    # 运行验证
    result = verifier.verify(market_a, market_b, mock_primary_analysis)

    print(f"\n验证结果:")
    print(f"  - Status: {result.status.value}")
    print(f"  - Overall Confidence: {result.overall_confidence:.2f}")
    print(f"  - Recommendation: {result.execution_recommendation}")

    if result.human_review_reasons:
        print(f"  - Review Reasons: {', '.join(result.human_review_reasons)}")

    print("\n测试完成！")
