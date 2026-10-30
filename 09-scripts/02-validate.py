#!/usr/bin/env python3
"""Check navigation, coverage, question/answer consistency and independent arithmetic."""
import ast
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
build = __import__("01-build-exams")
errors = []


def require(condition, message):
    if not condition:
        errors.append(message)


def slug(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text).replace("`", "").lower()
    return "".join(c for c in text if c in "-_" or not unicodedata.category(c).startswith(("P", "S"))).replace(" ", "-")


def arithmetic(expression):
    operators = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
                 ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
                 ast.Pow: lambda a, b: a ** b}
    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -evaluate(node.operand)
        raise ValueError("Only arithmetic expressions are accepted")
    return evaluate(ast.parse(expression, mode="eval").body)


def discount(amount, years, rate):
    for _ in range(years):
        amount /= 1 + rate
    return amount


def grow(amount, periods, rate):
    for _ in range(periods):
        amount *= 1 + rate
    return amount


def numeric_answer(item, expected):
    text = item["right"]["text"].replace(",", "").replace("−", "-")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    require(match is not None, "Missing numeric answer: " + item["question"])
    if not match:
        return
    number = match.group()
    decimals = len(number.split(".")[1]) if "." in number else 0
    tolerance = 0.5 * 10 ** (-decimals) + 1e-8
    require(abs(float(number) - expected) <= tolerance,
            f"Numeric mismatch: {item['question']} -> {number}, recomputed {expected}")


def main():
    markdown = {p.resolve(): p.read_text() for p in ROOT.rglob("*.md") if ".git" not in p.parts}
    adjacency = defaultdict(set)
    link_count = 0
    for path, text in markdown.items():
        require(text.startswith("# "), f"Missing title: {path.relative_to(ROOT)}")
        require(not re.search(r"turn\d+(?:search|view)\d+|TODO|TBD", text), f"Unresolved marker: {path}")
        body = re.sub(r"```.*?```", "", text, flags=re.S)
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", body):
            if re.match(r"^(?:https?://|mailto:)", target):
                continue
            dest, _, anchor = unquote(target).partition("#")
            resolved = (path.parent / dest).resolve() if dest else path
            link_count += 1
            require(resolved.exists(), f"Broken link: {path.relative_to(ROOT)} -> {target}")
            if resolved in markdown:
                adjacency[path].add(resolved)
                if anchor:
                    headings = {slug(h) for h in re.findall(r"^#{1,6} (.+)$", markdown[resolved], re.M)}
                    require(anchor in headings, f"Broken anchor: {path.relative_to(ROOT)} -> {target}")
    seen, pending = set(), [ROOT / "README.md"]
    while pending:
        path = pending.pop().resolve()
        if path in seen:
            continue
        seen.add(path)
        pending.extend(adjacency[path] - seen)
    require(set(markdown) <= seen, "Unreachable Markdown: " + str([str(p.relative_to(ROOT)) for p in set(markdown) - seen]))
    for directory in ROOT.iterdir():
        if directory.is_dir() and not directory.name.startswith("."):
            require(bool(re.match(r"\d{2}-", directory.name)), "Directory missing order number: " + directory.name)
    bank = json.loads((ROOT / "08-data/01-question-bank.json").read_text())
    require(len(bank) == 260, "Expected 260 MCQs")
    require(len({q["question"] for q in bank}) == 260, "Repeated question stems")
    for item in bank:
        choices = [item["right"], *item["wrong"]]
        require(len(choices) == 4 and len({x["text"] for x in choices}) == 4, "Repeated option: " + item["question"])
        require(all(x["explanation"] for x in choices), "Missing explanation")
    for chapter, (directory, _, prefix) in build.CHAPTERS.items():
        base = ROOT / "02-chapters" / directory
        for filename in ["00-overview.md", "01-core.md", "02-mechanisms.md", "03-practice.md", "04-summary.md", "05-exercises.md", "06-answers.md"]:
            require((base / filename).exists(), "Missing chapter file: " + str(base / filename))
        for filename in ["01-core.md", "02-mechanisms.md", "03-practice.md"]:
            text = (base / filename).read_text()
            require(len(re.findall(r"[\u4e00-\u9fff]", text)) >= 1000, "Incomplete lesson: " + str(base / filename))
        check_pair(base / "05-exercises.md", base / "06-answers.md", prefix, 20, bank)
    check_pair(ROOT / "06-exams/01-mock-a.md", ROOT / "06-exams/02-mock-a-answers.md", "MA", 60, bank)
    check_pair(ROOT / "06-exams/03-mock-b.md", ROOT / "06-exams/04-mock-b-answers.md", "MB", 60, bank)
    calculations = json.loads((ROOT / "08-data/02-calculations.json").read_text())
    require(len(calculations) == 30, "Expected 30 calculation exercises")
    for item in calculations:
        actual = arithmetic(item["expression"])
        require(math.isclose(actual, item["expected"], rel_tol=1e-10, abs_tol=1e-8), "Calculation mismatch: " + item["id"])
    require(len(re.findall(r"^\| D\d+ \|", (ROOT / "05-study/01-12-week-plan.md").read_text(), re.M)) == 84, "Expected 84 daily tasks")
    outcomes = re.findall(r"^\| (\d)\(([a-z])\) \|", (ROOT / "07-sources/03-coverage.md").read_text(), re.M)
    expected = {(str(ch), chr(97 + i)) for ch, count in {1:12, 2:10, 3:6, 4:8, 5:9, 6:8, 7:1}.items() for i in range(count)}
    require(set(outcomes) == expected and len(outcomes) == 54, "Missing or duplicate ELO identifiers")
    numeric_count = audit_bank_arithmetic(bank)
    if errors:
        print("\n".join(errors))
        raise SystemExit(f"FAILED: {len(errors)} problems")
    stats = {"markdown_files": len(markdown), "chinese_characters": sum(len(re.findall(r"[\u4e00-\u9fff]", s)) for s in markdown.values()),
             "local_links": link_count, "mcqs": len(bank), "calculation_exercises": 30, "foundation_questions": 20,
             "numeric_mcqs_recomputed": numeric_count, "elo_mappings": 54, "daily_tasks": 84}
    print(json.dumps({"status": "PASS", **stats}, ensure_ascii=False, indent=2))


def check_pair(qfile, afile, prefix, count, bank):
    text, answer_text = qfile.read_text(), afile.read_text()
    qblocks = re.split(r"^### (" + prefix + r"\d{2})\s*$", text, flags=re.M)
    ablocks = re.split(r"^### (" + prefix + r"\d{2})\s*$", answer_text, flags=re.M)
    questions = dict(zip(qblocks[1::2], qblocks[2::2]))
    answers = dict(zip(ablocks[1::2], ablocks[2::2]))
    wanted = {f"{prefix}{i:02}" for i in range(1, count + 1)}
    require(set(questions) == set(answers) == wanted, f"Question/answer IDs: {qfile}")
    letters = []
    by_stem = {item["question"]: item for item in bank}
    for identifier, block in questions.items():
        options = dict(re.findall(r"^([ABCD])\. (.+)$", block, re.M))
        require(set(options) == set("ABCD"), "Missing option: " + identifier)
        match = re.search(r"正确答案：([ABCD])", answers.get(identifier, ""))
        require(match is not None, "Missing answer key: " + identifier)
        if match:
            letter = match.group(1)
            letters.append(letter)
            stem = next((line.strip() for line in block.splitlines() if line.strip()), "")
            require(stem in by_stem, "Question absent from authored bank: " + identifier)
            if stem in by_stem:
                require(options.get(letter) == by_stem[stem]["right"]["text"], "Answer key points to wrong option: " + identifier)
            for wrong in set("ABCD") - {letter}:
                require(f"- {wrong}「" in answers[identifier], "Missing distractor explanation: " + identifier)
    require(Counter(letters) == dict.fromkeys("ABCD", count // 4), "Answer positions unbalanced: " + str(qfile))


def audit_bank_arithmetic(bank):
    grouped = defaultdict(list)
    for item in bank:
        grouped[item["kind"], item["chapter"]].append(item)
    checks = {
        1: {1: 20000-16000, 16: 10.02-9.98},
        2: {8: 1e6*(1-.02), 16: 1e6*(.06-.04)},
        3: {3: (22-20+1)/20*100, 4: (4*12+8)/5, 5: 12-(4*12+8)/5, 6: 2*15/3, 8:30/2, 10:12/8, 11:2/(.1-.02), 13:8*1e6},
        4: {1:2000*.04/2, 2:1000*.05, 4:(grow(1,2,.04)-1)*100, 5:(1.06/1.04-1)*100,
            7:discount(1000,1,.05), 8:discount(50,1,.06)+discount(1050,2,.06), 10:50/950*100,
            14:980+12, 15:300/100000*12*100, 18:(.05-.03)*10000},
        5: {2:1000*7.81, 3:1.1*7.8, 4:7.8/7.2, 5:(7.82/7.8-1)*2*100, 10:2-3, 11:10-2, 14:3*50*2, 18:6/10, 20:2500/1.0125},
        6: {11:-4*.005*100, 17:100-2-97},
        7: {2:300000-100000, 5:discount(60000,1,.1)+discount(60000,2,.1)-100000, 9:(.6*.1+.3*.02)*100, 10:(1020000-20000)/100000},
    }
    count = 0
    for chapter, mapping in checks.items():
        for index, expected in mapping.items():
            numeric_answer(grouped["chapter", chapter][index-1], expected)
            count += 1
    for k, form in enumerate(["a", "b"]):
        ch1 = {1:[8000,13000][k], 6:[35,50][k]}
        ch2 = {4:[25000*(7.83-7.77),18000*(7.84-7.76)][k],5:[800000*.015,600000*.025][k]}
        ch3 = {1:[(35-32+1.5)/32*100,(42-45+2.5)/45*100][k],2:[16,22][k],3:[18,14][k],4:12,5:1.5,
               6:[1.5*1.04/(.1-.04),2*1.03/(.11-.03)][k],7:[14e6,13.5e6][k],8:[6.4,5.2][k]}
        ch4 = {1:[discount(2000,2,.04),discount(1500,3,.06)][k],2:[discount(40,1,.05)+discount(1040,2,.05),discount(120,1,.04)+discount(2120,2,.04)][k],
               3:[150,60][k],4:[(grow(1,4,.015)-1)*100,(grow(1,2,.05)-1)*100][k],5:[(1.08/1.03-1)*100,(1.05/1.07-1)*100][k],
               6:[60/960*100,80/1040*100][k],7:[1.8,3.6][k],8:[220,180][k]}
        ch5 = {1:[7.78*2000,7.77*1500][k],2:[1.2*7.8,1.15*7.82][k],3:[(7.76/7.8-1)*4*100,(7.86/7.8-1)*2*100][k],
               4:[8*1.03/1.05,6*1.03/1.01][k],5:[3,-3][k],6:[-5,4][k],7:[360,-400][k],8:[156800,117150][k],
               9:[2000000*.02*.25/1.015,1000000*.02*.5/1.035][k]}
        ch6 = {2:[45000,30000][k],3:[2000,2250][k],4:[3.8,3][k],7:[4,5][k]}
        ch7 = {1:[150000,160000][k],2:80,3:[discount(30000,1,.08)+discount(28000,2,.08)-50000,discount(45000,1,.12)+discount(50000,2,.12)-80000][k],
               4:[3,-5][k],5:[-4.5,-5][k],6:[210000,153750][k]}
        for chapter, mapping in enumerate([ch1,ch2,ch3,ch4,ch5,ch6,ch7],1):
            for index, expected in mapping.items():
                numeric_answer(grouped[f"mock-{form}",chapter][index-1],expected)
                count += 1
    return count


if __name__ == "__main__":
    main()
