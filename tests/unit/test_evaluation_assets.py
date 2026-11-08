from pathlib import Path
from xml.etree import ElementTree


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_mcp_evaluation_has_ten_stable_qa_pairs() -> None:
    evaluation_path = (
        PROJECT_ROOT
        / "evaluations"
        / "mcp"
        / "researchflow_eval.xml"
    )
    root = ElementTree.parse(evaluation_path).getroot()
    pairs = root.findall("qa_pair")

    assert len(pairs) == 10
    for pair in pairs:
        question = pair.findtext("question", "").strip()
        answer = pair.findtext("answer", "").strip()
        assert question
        assert answer
        assert "当前" not in question
