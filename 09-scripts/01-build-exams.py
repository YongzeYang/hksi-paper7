#!/usr/bin/env python3
"""Render the authored question bank into chapter exercises and two mock exams."""
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAPTERS = {
    1: ("01-global", "全球金融体系", "G"),
    2: ("02-hk", "香港金融体系", "H"),
    3: ("03-equity", "股票市场", "E"),
    4: ("04-debt", "债务市场", "D"),
    5: ("05-fx-derivatives", "外汇与衍生工具", "F"),
    6: ("06-risk", "金融风险管理", "R"),
    7: ("07-applications", "金融业应用", "A"),
}
LESSONS = {1: "01-core.md", 2: "02-mechanisms.md", 3: "03-practice.md"}
LETTERS = "ABCD"


def render(items, prefix, output, answers, chapter=None, seed=0):
    rng = random.Random(seed)
    positions = list(range(4)) * (len(items) // 4)
    rng.shuffle(positions)
    title = f"第{chapter}章：{CHAPTERS[chapter][1]}20题" if chapter else f"模拟卷{prefix[-1]}：60题"
    parent = "../../README.md" if chapter else "../README.md"
    intro = "原创教学题，四选一，每题只有一个正确选项。先独立作答，再打开解析。"
    if not chapter:
        intro += "连续90分钟，60题，教学计分每题1分；42/60对应70%。章节分布为教学设计，不代表官方比例，也不保证正式试题难度。"
    question_lines = [f"# {title}", "", f"[总目录]({parent}) · [独立解析]({answers.name})", "", intro, ""]
    answer_lines = [f"# {title}：答案与解析", "", f"[总目录]({parent}) · [返回题目]({output.name})", "", "先完成题目。每题解析包含正确理由、逐个错误选项的问题与补学位置。", "", "| 题号 | 答案 |", "|---|---|"]
    details = []
    for i, (item, position) in enumerate(zip(items, positions), 1):
        identifier = f"{prefix}{i:02d}"
        distractors = list(item["wrong"])
        rng.shuffle(distractors)
        options = []
        for index in range(4):
            options.append(item["right"] if index == position else distractors.pop())
        correct = LETTERS[position]
        question_lines.extend([f"### {identifier}", "", item["question"], ""])
        question_lines.extend(f"{letter}. {option['text']}\n" for letter, option in zip(LETTERS, options))
        question_lines.extend(["", f"[本题解析]({answers.name}#{identifier.lower()})", ""])
        answer_lines.append(f"| [{identifier}]({output.name}#{identifier.lower()}) | {correct} |")
        review = LESSONS[item["lesson"]]
        if not chapter:
            review = f"../02-chapters/{CHAPTERS[item['chapter']][0]}/{review}"
        details.extend([f"### {identifier}", "", f"**正确答案：{correct}。** {item['right']['explanation']}", ""])
        for letter, option in zip(LETTERS, options):
            if letter != correct:
                details.append(f"- {letter}「{option['text']}」：{option['explanation']}")
        details.extend(["", f"补学：[第{item['chapter']}章相关正文]({review})。先遮住选项，重新解释，再做一次。", ""])
    question_lines.extend(["## 作答记录", "", "按题号记录：答案 / 确信或猜测 / 用时。查看解析后，将误区和补学动作写入错题本。", "", f"[查看解析]({answers.name}) · [总目录]({parent})", ""])
    answer_lines.extend(["", *details, "## 复盘", "", "把答对但无法解释的题也列入回补。一次分数只反映本套练习，不保证正式考试结果。", "", f"[返回题目]({output.name}) · [总目录]({parent})", ""])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(question_lines))
    answers.write_text("\n".join(answer_lines))


def main():
    bank = json.loads((ROOT / "08-data/01-question-bank.json").read_text())
    assert len(bank) == 260
    assert len({item["question"] for item in bank}) == len(bank), "Repeated question stem"
    for item in bank:
        assert len(item["wrong"]) == 3
        texts = [item["right"]["text"]] + [o["text"] for o in item["wrong"]]
        assert len(set(texts)) == 4, item["question"]
        assert all(o["explanation"] for o in [item["right"], *item["wrong"]])
    for chapter, (directory, _, prefix) in CHAPTERS.items():
        questions = [x for x in bank if x["kind"] == "chapter" and x["chapter"] == chapter]
        assert len(questions) == 20
        base = ROOT / "02-chapters" / directory
        render(questions, prefix, base / "05-exercises.md", base / "06-answers.md", chapter, 700 + chapter)
    for form, qname, aname in [
        ("a", "01-mock-a.md", "02-mock-a-answers.md"),
        ("b", "03-mock-b.md", "04-mock-b-answers.md"),
    ]:
        questions = [x for x in bank if x["kind"] == f"mock-{form}"]
        assert len(questions) == 60
        assert Counter(x["chapter"] for x in questions) == {1: 8, 2: 8, 3: 9, 4: 9, 5: 9, 6: 9, 7: 8}
        random.Random(7100 + ord(form)).shuffle(questions)
        render(questions, f"M{form.upper()}", ROOT / "06-exams" / qname, ROOT / "06-exams" / aname, seed=7200 + ord(form))
    print("Rendered 140 chapter questions and 120 independent mock questions with explanations.")


if __name__ == "__main__":
    main()
