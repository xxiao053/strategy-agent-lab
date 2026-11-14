"""User-requested settings affect new runs, never historical experiment versions."""
from lab.account import Account, quantity
from lab.contracts import Strategy, RunConfig
from lab.store import Store
from tests.helpers import exit_facts


def test_new_default_risk_budget_sizes_wide_stop_at_five_percent():
    # E=100000, M=103, S=1, per-share planned risk=102.052.
    # The $5000 risk budget permits 48 whole shares; weight/cash do not bind.
    assert quantity(100000, 100, 1, 100000, Strategy()) == 48


def test_new_default_allows_five_reserved_and_held_slots():
    # Leave enough cash for a sixth entry so only the slot limit rejects it.
    strategy = Strategy(max_weight=.1)
    account = Account(100000)
    for symbol in ['A', 'B', 'C', 'D', 'E']:
        assert account.enter(symbol, '2024-01-02', 100, 99, strategy, pattern=exit_facts(99))
    assert not account.enter('F', '2024-01-02', 100, 99, strategy, pattern=exit_facts(99))
    account.open_day('2024-01-03', dict.fromkeys(['A', 'B', 'C', 'D', 'E'], 100), strategy)
    assert len(account.positions) == 5
    assert account.cash > 40000
    assert not account.enter('F', '2024-01-03', 100, 99, strategy, pattern=exit_facts(99))


def test_new_defaults_do_not_change_saved_previous_configuration(tmp_path):
    store = Store(tmp_path/'lab.sqlite3')
    legacy = RunConfig(strategy=Strategy(risk_fraction=.005, max_positions=3))
    saved = store.create(legacy.model_dump(), {}, 'frozen-source')
    new = RunConfig()
    restored = RunConfig.model_validate(store.get(saved['id'])['config'])
    assert quantity(100000, 100, 1, 100000, restored.strategy) == 4
    assert quantity(100000, 100, 1, 100000, new.strategy) == 48
    assert restored.strategy.max_positions == 3
