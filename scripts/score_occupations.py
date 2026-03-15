"""
Score Chinese occupations for AI replacement susceptibility using Claude API.
Each occupation gets a score from 0-10.
"""
import json
import os
import time
import hashlib
from pathlib import Path
from anthropic import Anthropic

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_DIR = DATA_DIR / "score_cache"
CACHE_DIR.mkdir(exist_ok=True)

SCORING_PROMPT = """你是一位AI和自动化领域的专家分析师。请评估以下中国职业被AI和自动化技术替代的可能性。

## 评分标准（0-10分）

**核心判断维度：**

1. **工作产出的数字化程度**（权重最高）
   - 工作成果是否主要是数字化的（文本、代码、数据、设计文件等）？
   - 数字化产出越多，AI替代可能性越高

2. **远程工作可行性**
   - 该工作是否可以完全在电脑前完成？
   - 如果可以远程完成，说明工作的物理依赖性低，AI更容易替代

3. **体力劳动和物理操作需求**
   - 是否需要精细的手工操作、体力劳动、或在特定物理环境中工作？
   - 物理操作需求越高，当前AI/机器人替代难度越大

4. **人际互动和情感判断**
   - 是否需要面对面的人际沟通、情感支持、信任建立？
   - 高度依赖人际关系的工作更难被替代

5. **创造性和非结构化决策**
   - 工作是否涉及高度创造性、复杂判断、或处理全新未知情况？
   - 纯创造性工作比模式化工作更难替代（但注意：很多"创造性"工作实际上是模式化的）

6. **监管和制度约束**
   - 是否存在法律、政策、伦理等因素限制AI在该领域的应用？
   - 注意：这影响替代速度，但不影响技术可行性评分

## 评分刻度

- **0-1分**：几乎不可能被AI替代。需要大量体力劳动、在复杂物理环境中操作。如：建筑工人、环卫工人、矿工
- **2-3分**：替代难度很高。需要精细手工操作或特定物理环境。如：厨师、护士、电工
- **4-5分**：中等替代可能。部分工作可自动化但仍需人工参与。如：医生、零售人员、警察
- **6-7分**：较高替代可能。大部分工作可由AI完成，人工主要做监督和例外处理。如：会计、银行柜员、客服
- **8-9分**：非常高的替代可能。工作产出几乎完全数字化，AI已能完成大部分任务。如：软件开发、数据分析、翻译、文案写作
- **10分**：几乎确定被替代。工作完全数字化且高度模式化。如：数据录入、医学转录

## 要求

请对以下职业进行评分。返回JSON格式，包含：
- score: 0-10的整数评分
- reasoning: 简短的评分理由（1-2句话）
- digital_output: 工作产出数字化程度（low/medium/high）
- physical_demand: 体力/物理操作需求（low/medium/high）
- remote_feasibility: 远程工作可行性（low/medium/high）

## 职业信息

职业编码：{code}
职业名称：{name}
所属大类：{major_category}
所属中类：{middle_category}
所属小类：{minor_category}

请只返回JSON，不要有其他内容。
"""


def get_cache_path(code: str) -> Path:
    return CACHE_DIR / f"{code}.json"


def load_cached_score(code: str) -> dict | None:
    path = get_cache_path(code)
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_cached_score(code: str, result: dict):
    path = get_cache_path(code)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))


def score_occupation(client: Anthropic, occupation: dict, categories: dict) -> dict:
    """Score a single occupation using Claude API."""
    code = occupation["code"]

    # Check cache
    cached = load_cached_score(code)
    if cached:
        return cached

    # Build context
    major_name = categories["major"].get(occupation["major"], "")
    middle_name = categories["middle"].get(occupation["middle"], "")
    minor_name = categories["minor"].get(occupation["minor"], "")

    prompt = SCORING_PROMPT.format(
        code=code,
        name=occupation["name"],
        major_category=f"{occupation['major']} {major_name}",
        middle_category=f"{occupation['middle']} {middle_name}",
        minor_category=f"{occupation['minor']} {minor_name}",
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = response.content[0].text.strip()

    # Parse JSON from response
    # Handle potential markdown code blocks
    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            result = json.loads(match.group())
        else:
            result = {
                "score": -1,
                "reasoning": f"Failed to parse: {response_text[:200]}",
                "digital_output": "unknown",
                "physical_demand": "unknown",
                "remote_feasibility": "unknown",
            }

    # Add metadata
    result["code"] = code
    result["name"] = occupation["name"]

    # Cache result
    save_cached_score(code, result)
    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Score occupations for AI replacement")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of occupations to score (0 = all)")
    parser.add_argument("--batch-size", type=int, default=10, help="Pause every N requests")
    parser.add_argument("--major", type=str, default="", help="Only score occupations in this major category (1-8)")
    args = parser.parse_args()

    # Load data
    with open(DATA_DIR / "occupations_raw.json") as f:
        data = json.load(f)

    occupations = data["occupations"]
    categories = {
        "major": data["major_categories"],
        "middle": data["middle_categories"],
        "minor": data["minor_categories"],
    }

    # Filter
    if args.major:
        occupations = [o for o in occupations if o["major"] == args.major]

    if args.limit:
        occupations = occupations[:args.limit]

    # Count already cached
    cached_count = sum(1 for o in occupations if load_cached_score(o["code"]))
    print(f"Total occupations to score: {len(occupations)}")
    print(f"Already cached: {cached_count}")
    print(f"Remaining: {len(occupations) - cached_count}")

    if cached_count == len(occupations):
        print("All occupations already scored!")
    else:
        client = Anthropic()
        scored = 0
        errors = 0

        for i, occ in enumerate(occupations):
            if load_cached_score(occ["code"]):
                continue

            try:
                result = score_occupation(client, occ, categories)
                scored += 1
                score = result.get("score", "?")
                print(f"[{i+1}/{len(occupations)}] {occ['code']} {occ['name']}: {score}/10")

                # Rate limiting
                if scored % args.batch_size == 0:
                    time.sleep(1)

            except Exception as e:
                errors += 1
                print(f"[{i+1}/{len(occupations)}] ERROR {occ['code']} {occ['name']}: {e}")
                if errors > 10:
                    print("Too many errors, stopping.")
                    break
                time.sleep(2)

        print(f"\nDone. Scored: {scored}, Errors: {errors}")

    # Compile all results
    all_results = []
    for occ in data["occupations"]:  # Use full list, not filtered
        result = load_cached_score(occ["code"])
        if result:
            all_results.append(result)

    if all_results:
        output_path = DATA_DIR / "scores.json"
        with open(output_path, "w") as f:
            json.dump({
                "total_scored": len(all_results),
                "scores": sorted(all_results, key=lambda x: x.get("score", -1), reverse=True),
            }, f, ensure_ascii=False, indent=2)
        print(f"Compiled {len(all_results)} scores to {output_path}")

        # Print summary
        from collections import Counter
        score_dist = Counter(r.get("score", -1) for r in all_results)
        print("\nScore distribution:")
        for s in range(11):
            count = score_dist.get(s, 0)
            bar = "█" * count
            print(f"  {s:2d}: {count:4d} {bar}")


if __name__ == "__main__":
    main()
