"""Parse the 职业分类大典 PDF to extract structured occupation data."""
import subprocess
import re
import json

PDF_PATH = "/Users/verypro/.claude/projects/-Users-verypro-china-jobs/771fe326-d7d1-4382-83d3-42167d2d2ff4/tool-results/webfetch-1773581296876-bdl869.pdf"

result = subprocess.run(["pdftotext", "-raw", PDF_PATH, "-"], capture_output=True, text=True)
raw_lines = result.stdout.split('\n')

# Join continuation lines: if a line doesn't start with a code pattern or header, append to previous
lines = []
for line in raw_lines:
    stripped = line.strip()
    if not stripped:
        continue
    # Check if this line starts with a code pattern like "1 - 01" or a header
    if re.match(r'^\d\s*-\s*\d', stripped) or re.match(r'^第.大类', stripped) or re.match(r'^中类', stripped) or re.match(r'^续表', stripped) or re.match(r'^\d+\s*\d*$', stripped) or re.match(r'^分类体系表', stripped) or re.match(r'^中华人民共和国', stripped) or re.match(r'^职\s*业\s*分\s*类', stripped):
        lines.append(stripped)
    elif lines:
        lines[-1] += stripped
    else:
        lines.append(stripped)

# Now normalize spaces in codes: "1 - 0 1 - 0 0 - 0 1" -> "1-01-00-01"
def normalize_code(s):
    """Remove spaces around dashes and between digits in codes."""
    # First normalize "1 - 0 1 - 0 0 - 0 1" style
    s = re.sub(r'(\d)\s*-\s*(\d)\s*(\d)\s*-\s*(\d)\s*(\d)\s*-\s*(\d)\s*(\d)',
               lambda m: f"{m.group(1)}-{m.group(2)}{m.group(3)}-{m.group(4)}{m.group(5)}-{m.group(6)}{m.group(7)}", s)
    # Also normalize "1 - 0 1 - 0 0" (3-level)
    s = re.sub(r'(\d)\s*-\s*(\d)\s*(\d)\s*-\s*(\d)\s*(\d)',
               lambda m: f"{m.group(1)}-{m.group(2)}{m.group(3)}-{m.group(4)}{m.group(5)}", s)
    # Also normalize "1 - 0 1" (2-level)
    s = re.sub(r'(\d)\s*-\s*(\d)\s*(\d)',
               lambda m: f"{m.group(1)}-{m.group(2)}{m.group(3)}", s)
    # Handle "1 - 9 9" style
    s = re.sub(r'(\d)\s*-\s*(\d)\s+(\d)',
               lambda m: f"{m.group(1)}-{m.group(2)}{m.group(3)}", s)
    return s

# Normalize GBM codes too
def normalize_gbm(s):
    s = re.sub(r'G\s*B\s*M\s*', 'GBM', s)
    # Remove spaces in GBM numbers: "GBM1 0 1 0 0" -> "GBM10100"
    def fix_gbm(m):
        digits = re.sub(r'\s+', '', m.group(1))
        return f"GBM{digits}"
    s = re.sub(r'GBM([\d\s]+)', fix_gbm, s)
    return s

normalized = []
for line in lines:
    line = normalize_code(line)
    line = normalize_gbm(line)
    normalized.append(line)

# Now extract data
major_categories = {}  # code -> name
middle_categories = {}
minor_categories = {}
occupations = []

# Patterns
major_pat = re.compile(r'第.大类\s*(\d)\s*[（(]GBM\d+[)）]\s*(.+)')
middle_pat = re.compile(r'^(\d-\d{2})\s*\(GBM\d+\)\s*(.+)')
minor_pat = re.compile(r'^(\d-\d{2}-\d{2})\s*\(GBM\d+\s*\)\s*(.+)')
# 细类 pattern: 4-level code NOT followed by (GBM...)
occ_pat = re.compile(r'^(\d-\d{2}-\d{2}-\d{2})\s+(.+)')

for line in normalized:
    # Major category
    m = major_pat.match(line)
    if m:
        major_categories[m.group(1)] = m.group(2).strip()
        continue

    # Occupation (4-level) - check before minor to avoid confusion
    m = occ_pat.match(line)
    if m and '(GBM' not in line and 'GBM' not in m.group(2)[:10]:
        code = m.group(1)
        name = m.group(2).strip()
        # Remove trailing L, S, L/S markers and page numbers
        name = re.sub(r'\s*[LS]\s*/\s*[LS]\s*$', '', name)
        name = re.sub(r'\s+[LS]$', '', name)
        name = re.sub(r'\s*\d+\s*\d*$', '', name)  # trailing page numbers
        # Remove spaces within Chinese characters
        name = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', name)
        # Clean trailing markers
        name = name.rstrip()
        if name:
            occupations.append({
                "code": code,
                "major": code[0],
                "middle": code[:4],
                "minor": code[:7],
                "name": name
            })
        continue

    # Middle category (2-level with GBM)
    m = middle_pat.match(line)
    if m:
        code = m.group(1)
        name = m.group(2).strip()
        name = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', name)
        middle_categories[code] = name
        continue

    # Minor category (3-level with GBM)
    m = minor_pat.match(line)
    if m:
        code = m.group(1)
        name = m.group(2).strip()
        name = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', name)
        minor_categories[code] = name
        continue

# Deduplicate occupations
seen = set()
unique_occs = []
for occ in occupations:
    if occ['code'] not in seen:
        seen.add(occ['code'])
        unique_occs.append(occ)
occupations = sorted(unique_occs, key=lambda x: x['code'])

print(f"Major categories ({len(major_categories)}):")
for k, v in sorted(major_categories.items()):
    print(f"  {k}: {v}")

print(f"\nMiddle categories: {len(middle_categories)}")
print(f"Minor categories: {len(minor_categories)}")
print(f"Occupations (细类): {len(occupations)}")

# Build hierarchical output
output = {
    "source": "中华人民共和国职业分类大典（2022年版）",
    "stats": {
        "major_categories": len(major_categories),
        "middle_categories": len(middle_categories),
        "minor_categories": len(minor_categories),
        "occupations": len(occupations)
    },
    "major_categories": {k: v for k, v in sorted(major_categories.items())},
    "middle_categories": {k: v for k, v in sorted(middle_categories.items())},
    "minor_categories": {k: v for k, v in sorted(minor_categories.items())},
    "occupations": occupations
}

with open("/Users/verypro/china-jobs/data/occupations_raw.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nWrote to data/occupations_raw.json")
print("\nSample occupations:")
for occ in occupations[:15]:
    print(f"  {occ['code']}: {occ['name']}")
print("  ...")
for occ in occupations[-10:]:
    print(f"  {occ['code']}: {occ['name']}")

# Stats per major category
from collections import Counter
major_counts = Counter(o['major'] for o in occupations)
print("\nPer major category:")
for k in sorted(major_counts):
    name = major_categories.get(k, "?")
    print(f"  {k} ({name}): {major_counts[k]} occupations")
