from collections import defaultdict, deque
from collections.abc import Iterable


def has_cycle(edges: Iterable[tuple[int, int]]) -> bool:
    adjacency: dict[int, set[int]] = defaultdict(set)
    indegree: dict[int, int] = defaultdict(int)
    nodes: set[int] = set()
    for source, target in edges:
        nodes.update((source, target))
        if target not in adjacency[source]:
            adjacency[source].add(target)
            indegree[target] += 1
        indegree.setdefault(source, 0)
    queue = deque(node for node in nodes if indegree[node] == 0)
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for target in adjacency[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return visited != len(nodes)


def normalize_title(value: str) -> str:
    return "".join(character.casefold() for character in value.strip() if character.isalnum())
