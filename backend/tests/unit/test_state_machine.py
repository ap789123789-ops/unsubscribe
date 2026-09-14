import pytest

from app.domain.state_machine import ActionState, InvalidTransition, transition_action


def test_selected_action_can_be_confirmed_started_and_submitted() -> None:
    assert (
        transition_action(ActionState.SELECTED, ActionState.CONFIRMED_BY_USER)
        is ActionState.CONFIRMED_BY_USER
    )
    assert (
        transition_action(ActionState.CONFIRMED_BY_USER, ActionState.EXECUTING)
        is ActionState.EXECUTING
    )
    assert transition_action(ActionState.EXECUTING, ActionState.SUBMITTED) is ActionState.SUBMITTED


def test_terminal_action_cannot_execute_again() -> None:
    with pytest.raises(InvalidTransition):
        transition_action(ActionState.SUBMITTED, ActionState.EXECUTING)
