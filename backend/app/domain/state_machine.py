from enum import StrEnum


class ActionState(StrEnum):
    DISCOVERED = "discovered"
    REVIEWED = "reviewed"
    SELECTED = "selected"
    CONFIRMED_BY_USER = "confirmed_by_user"
    EXECUTING = "executing"
    CONFIRMED = "confirmed"
    SUBMITTED = "submitted"
    NEEDS_USER = "needs_user"
    FAILED = "failed"


class InvalidTransition(ValueError):
    pass


ALLOWED_ACTION_TRANSITIONS: dict[ActionState, frozenset[ActionState]] = {
    ActionState.DISCOVERED: frozenset({ActionState.REVIEWED}),
    ActionState.REVIEWED: frozenset({ActionState.SELECTED}),
    ActionState.SELECTED: frozenset({ActionState.REVIEWED, ActionState.CONFIRMED_BY_USER}),
    ActionState.CONFIRMED_BY_USER: frozenset({ActionState.EXECUTING, ActionState.REVIEWED}),
    ActionState.EXECUTING: frozenset(
        {
            ActionState.CONFIRMED,
            ActionState.SUBMITTED,
            ActionState.NEEDS_USER,
            ActionState.FAILED,
        }
    ),
    ActionState.NEEDS_USER: frozenset({ActionState.EXECUTING, ActionState.REVIEWED}),
    ActionState.FAILED: frozenset({ActionState.REVIEWED}),
    ActionState.CONFIRMED: frozenset(),
    ActionState.SUBMITTED: frozenset(),
}


def transition_action(current: ActionState, target: ActionState) -> ActionState:
    if target not in ALLOWED_ACTION_TRANSITIONS[current]:
        raise InvalidTransition(f"Cannot transition action from {current} to {target}")
    return target


def recover_action(state: ActionState) -> ActionState:
    return ActionState.NEEDS_USER if state is ActionState.EXECUTING else state
