from app.analysis import run_all_checks
from tests.factories import make_board, make_component, make_net, make_trace, make_via


def test_ids_are_category_prefixed_and_sequential():
    board = make_board(
        components=[make_component("U1", "LM7805", "regulator", x=10, y=10)],
        nets=[
            make_net("+3V3", traces=[make_trace("+3V3", 0, 0, 5, 0, width=0.1)]),
            make_net("+5V", traces=[make_trace("+5V", 0, 0, 5, 0, width=0.1)]),
        ],
    )
    issues = run_all_checks(board)

    power_ids = [i.id for i in issues if i.category == "power"]
    assert power_ids == [f"PWR-{k:03d}" for k in range(1, len(power_ids) + 1)]
    assert all(i.id for i in issues), "every issue must get a non-empty id"


def test_ids_are_unique_across_categories():
    board = make_board(
        components=[make_component("U1", "LM7805", "regulator", x=10, y=10)],
        nets=[make_net("+3V3", traces=[make_trace("+3V3", 0, 0, 5, 0, width=0.1)])],
    )
    issues = run_all_checks(board)
    ids = [i.id for i in issues]
    assert len(ids) == len(set(ids))


def test_no_issues_no_ids_needed():
    board = make_board()
    assert run_all_checks(board) == []
