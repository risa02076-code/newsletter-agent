from langgraph.graph import END, START, StateGraph

from jobkorea import fetch_hr_postings
from state import State

NODE_NAMES = ["collect", "select", "draft", "verify", "publish"]


def collect(state: State) -> dict:
    postings = fetch_hr_postings(hours=state.get("hours", 24))
    return {"collected": postings, "log": [f"[collect] {len(postings)}건 수집 (잡코리아 인사·HR)"]}


def select(state: State) -> dict:
    return {"picked": [], "log": [f"[select] {len(state['collected'])}건 중 0건 선택 (스텁)"]}


def draft(state: State) -> dict:
    return {"drafted": [], "log": [f"[draft] {len(state['picked'])}건 요약 (스텁)"]}


def verify(state: State) -> dict:
    return {"log": [f"[verify] {len(state['drafted'])}건 검수 (스텁)"]}


def publish(state: State) -> dict:
    return {"log": ["[publish] 0건 발행 (스텁)"]}


def build():
    graph = StateGraph(State)
    for name in NODE_NAMES:
        graph.add_node(name, globals()[name])
    graph.add_edge(START, NODE_NAMES[0])
    for a, b in zip(NODE_NAMES, NODE_NAMES[1:]):
        graph.add_edge(a, b)
    graph.add_edge(NODE_NAMES[-1], END)
    return graph.compile()


if __name__ == "__main__":
    app = build()
    result = app.invoke({"hours": 24, "collected": [], "picked": [], "drafted": [], "log": []})
    for line in result["log"]:
        print(line)
